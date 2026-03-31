"""Container pool for Manus-style per-agent sandbox reuse.

Maintains a fixed pool of pre-warmed containers.  Callers ``lease()``
a container for an engagement and ``release()`` it when done.  If all
containers are leased the caller waits up to ``timeout_seconds``; if
the wait expires a ``ContainerPoolExhaustedError`` is raised.

Pool uses ``asyncio.Queue[str]`` for natural FIFO ordering with no
explicit locking.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from seraph.config import settings
from seraph.exceptions import ContainerPoolExhaustedError, SandboxError
from seraph.sandbox.manager import ContainerManager
from seraph.sandbox.models import ContainerSpec, PooledContainer

log = structlog.get_logger(__name__)


class ContainerPool:
    """Fixed-size pool of warm sandbox containers.

    Containers are created at ``initialize()`` time and reused across
    leases.  Dead containers are detected at release time and replaced
    automatically.

    Args:
        manager: ``ContainerManager`` used to create/remove containers.
        pool_size: Number of containers to maintain in the pool.
        timeout_seconds: How long ``lease()`` waits if the pool is empty.
        base_spec: Template ``ContainerSpec`` used for all pool containers.
    """

    def __init__(
        self,
        manager: ContainerManager,
        pool_size: int | None = None,
        timeout_seconds: int | None = None,
        base_spec: ContainerSpec | None = None,
    ) -> None:
        self._manager = manager
        self._pool_size = pool_size or settings.sandbox_pool_size
        self._timeout = timeout_seconds or settings.sandbox_pool_timeout_seconds
        self._base_spec = base_spec or ContainerSpec(
            agent_name="pool",
            image=settings.sandbox_image,
            cpu_limit=settings.sandbox_cpu_limit,
            memory_limit_mb=settings.sandbox_memory_limit_mb,
            timeout_seconds=settings.sandbox_container_timeout,
            network_name=settings.sandbox_network_name,
        )
        # Queue holds available container IDs.
        self._available: asyncio.Queue[str] = asyncio.Queue()
        # Full registry for replacement / shutdown.
        self._containers: dict[str, PooledContainer] = {}
        self._initialized = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Create and start all pool containers.

        Should be called once at application startup (or on first use).
        Idempotent — calling again when already initialized is a no-op.

        Raises:
            SandboxError: If any container fails to start.
        """
        if self._initialized:
            return
        log.info("sandbox.pool.initializing", pool_size=self._pool_size)
        for i in range(self._pool_size):
            spec = self._base_spec.model_copy(update={"agent_name": f"pool-{i}"})
            container_id = await self._create_and_start(spec)
            pooled = PooledContainer(
                container_id=container_id,
                agent_name=spec.agent_name,
                spec=spec,
            )
            self._containers[container_id] = pooled
            await self._available.put(container_id)

        self._initialized = True
        log.info("sandbox.pool.ready", pool_size=self._pool_size)

    async def shutdown(self) -> None:
        """Stop and remove all pool containers gracefully."""
        log.info("sandbox.pool.shutdown", count=len(self._containers))
        for container_id in list(self._containers):
            try:
                await self._manager.stop_container(container_id)
                await self._manager.remove_container(container_id)
            except Exception as exc:
                log.warning(
                    "sandbox.pool.shutdown_error",
                    container_id=container_id[:12],
                    error=str(exc),
                )
        self._containers.clear()
        self._initialized = False

    # ── Lease / release ───────────────────────────────────────────────────────

    async def lease(
        self,
        agent_name: str,
        target_ip: str = "",
        tools: list[str] | None = None,
    ) -> str:
        """Acquire a container from the pool.

        Blocks up to ``timeout_seconds`` if the pool is empty.

        Args:
            agent_name: Agent that will use the container.
            target_ip: Informational — the engagement target IP.
            tools: Informational — tools the agent will use.

        Returns:
            Container ID string.

        Raises:
            ContainerPoolExhaustedError: If no container is available within the timeout.
        """
        if not self._initialized:
            await self.initialize()

        log.debug("sandbox.pool.lease_request", agent_name=agent_name)
        try:
            container_id = await asyncio.wait_for(
                self._available.get(),
                timeout=float(self._timeout),
            )
        except TimeoutError as exc:
            raise ContainerPoolExhaustedError(
                f"No sandbox container available after {self._timeout}s "
                f"(pool_size={self._pool_size})"
            ) from exc

        # Verify it's still alive; replace if dead.
        if not await self._is_alive(container_id):
            log.warning(
                "sandbox.pool.dead_container",
                container_id=container_id[:12],
            )
            container_id = await self._replace(container_id)

        # Mark as leased.
        if container_id in self._containers:
            pooled = self._containers[container_id]
            self._containers[container_id] = pooled.model_copy(
                update={
                    "leased": True,
                    "leased_at": datetime.now(UTC),
                    "agent_name": agent_name,
                }
            )
        log.info(
            "sandbox.pool.leased",
            container_id=container_id[:12],
            agent_name=agent_name,
        )
        return container_id

    async def release(self, container_id: str) -> None:
        """Return a container to the pool.

        If the container is dead it will be replaced with a fresh one.

        Args:
            container_id: Container ID previously returned by ``lease()``.
        """
        log.debug("sandbox.pool.release", container_id=container_id[:12])

        if not await self._is_alive(container_id):
            log.warning(
                "sandbox.pool.replace_on_release",
                container_id=container_id[:12],
            )
            container_id = await self._replace(container_id)
        else:
            # Clear lease metadata.
            if container_id in self._containers:
                pooled = self._containers[container_id]
                self._containers[container_id] = pooled.model_copy(
                    update={"leased": False, "leased_at": None}
                )

        await self._available.put(container_id)
        log.info("sandbox.pool.released", container_id=container_id[:12])

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _create_and_start(self, spec: ContainerSpec) -> str:
        """Create, start, and health-check a single container.

        Returns:
            Container ID string.

        Raises:
            SandboxError: If creation or start fails.
        """
        info = await self._manager.create_container(spec)
        await self._manager.start_container(info.container_id)
        await self._manager.health_check(info.container_id)
        return info.container_id

    async def _is_alive(self, container_id: str) -> bool:
        """Return True if the container is still running."""
        from seraph.sandbox.models import ContainerStatus

        try:
            status = await self._manager.get_status(container_id)
            return status == ContainerStatus.RUNNING
        except SandboxError:
            return False

    async def _replace(self, dead_container_id: str) -> str:
        """Remove a dead container and spin up a replacement.

        Returns:
            New container ID.
        """
        # Clean up stale registry entry.
        old_pooled = self._containers.pop(dead_container_id, None)
        spec = old_pooled.spec if old_pooled else self._base_spec

        try:
            await self._manager.remove_container(dead_container_id, force=True)
        except SandboxError:
            pass  # already gone

        new_id = await self._create_and_start(spec)
        self._containers[new_id] = PooledContainer(
            container_id=new_id,
            agent_name=spec.agent_name,
            spec=spec,
        )
        log.info(
            "sandbox.pool.replaced",
            old=dead_container_id[:12],
            new=new_id[:12],
        )
        return new_id
