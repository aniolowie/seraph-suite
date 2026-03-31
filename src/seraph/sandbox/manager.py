"""Docker container lifecycle management for Seraph sandbox.

Provides create/start/stop/remove/health-check operations over aiodocker.
All containers are labelled with ``seraph.agent`` and ``seraph.managed``
so they can be found and cleaned up independently of pool state.
"""

from __future__ import annotations

import asyncio

import structlog

from seraph.exceptions import ContainerHealthCheckError, ContainerStartError, SandboxError
from seraph.sandbox.models import ContainerInfo, ContainerSpec, ContainerStatus

log = structlog.get_logger(__name__)

# Labels applied to every Seraph-managed container.
_LABEL_MANAGED = "seraph.managed"
_LABEL_AGENT = "seraph.agent"
_LABEL_ENGAGEMENT = "seraph.engagement"

# Maximum number of health-check retries before raising.
_HEALTH_CHECK_RETRIES = 10
_HEALTH_CHECK_INTERVAL = 1.0  # seconds


class ContainerManager:
    """Manages the full lifecycle of sandbox containers.

    Wraps aiodocker to provide typed, async create/start/stop/remove
    and health-check primitives.

    Args:
        docker_client: An ``aiodocker.Docker`` instance.
    """

    def __init__(self, docker_client: object) -> None:
        self._docker = docker_client

    # ── Creation / destruction ────────────────────────────────────────────────

    async def create_container(self, spec: ContainerSpec) -> ContainerInfo:
        """Create (but do not start) a container from a ``ContainerSpec``.

        Args:
            spec: Desired container configuration.

        Returns:
            ``ContainerInfo`` with status ``CREATED``.

        Raises:
            ContainerStartError: If Docker rejects the create request.
        """
        log.info(
            "sandbox.manager.create",
            agent=spec.agent_name,
            image=spec.image,
        )
        labels = {
            _LABEL_MANAGED: "true",
            _LABEL_AGENT: spec.agent_name,
            **spec.labels,
        }

        # Build host-config for resource limits.
        # cpu_period=100_000µs is the Docker default; cpu_quota derives cores.
        cpu_quota = int(spec.cpu_limit * 100_000)
        memory_bytes = spec.memory_limit_mb * 1024 * 1024

        host_config: dict[str, object] = {
            "CpuQuota": cpu_quota,
            "CpuPeriod": 100_000,
            "Memory": memory_bytes,
            "MemorySwap": memory_bytes,  # disable swap
            "NetworkMode": spec.network_name or "bridge",
            "Binds": [f"{host}:{container}" for host, container in spec.volumes.items()],
        }

        config: dict[str, object] = {
            "Image": spec.image,
            "Cmd": ["sleep", "infinity"],
            "Labels": labels,
            "Env": [f"{k}={v}" for k, v in spec.environment.items()],
            "HostConfig": host_config,
        }

        try:
            container = await self._docker.containers.create(config)
            container_id: str = container.id
            log.info(
                "sandbox.manager.created",
                container_id=container_id[:12],
                agent=spec.agent_name,
            )
            return ContainerInfo(
                container_id=container_id,
                agent_name=spec.agent_name,
                status=ContainerStatus.CREATED,
                spec=spec,
            )
        except Exception as exc:
            raise ContainerStartError(
                f"Failed to create container for agent {spec.agent_name!r}: {exc}"
            ) from exc

    async def start_container(self, container_id: str) -> ContainerInfo:
        """Start a previously created container.

        Args:
            container_id: Full Docker container ID.

        Returns:
            ``ContainerInfo`` with status ``RUNNING`` and IP address populated.

        Raises:
            ContainerStartError: If the container fails to start.
        """
        log.info("sandbox.manager.start", container_id=container_id[:12])
        try:
            container = self._docker.containers.container(container_id)
            await container.start()
            info = await container.show()

            # Extract IP from the first network.
            networks = info.get("NetworkSettings", {}).get("Networks", {})
            ip_address = ""
            for net_info in networks.values():
                ip_address = net_info.get("IPAddress", "")
                if ip_address:
                    break

            agent_name: str = info.get("Config", {}).get("Labels", {}).get(_LABEL_AGENT, "")
            spec_image: str = info.get("Config", {}).get("Image", "")
            # Reconstruct a minimal spec for ContainerInfo.
            spec = ContainerSpec(agent_name=agent_name, image=spec_image)

            log.info(
                "sandbox.manager.started",
                container_id=container_id[:12],
                ip=ip_address,
            )
            return ContainerInfo(
                container_id=container_id,
                agent_name=agent_name,
                status=ContainerStatus.RUNNING,
                ip_address=ip_address,
                spec=spec,
            )
        except Exception as exc:
            raise ContainerStartError(
                f"Failed to start container {container_id[:12]!r}: {exc}"
            ) from exc

    async def stop_container(self, container_id: str, timeout: int = 10) -> None:
        """Gracefully stop a running container.

        Args:
            container_id: Full Docker container ID.
            timeout: Seconds to wait for graceful shutdown before SIGKILL.

        Raises:
            SandboxError: On unexpected Docker error.
        """
        log.info("sandbox.manager.stop", container_id=container_id[:12])
        try:
            container = self._docker.containers.container(container_id)
            await container.stop(t=timeout)
            log.info("sandbox.manager.stopped", container_id=container_id[:12])
        except Exception as exc:
            raise SandboxError(f"Failed to stop container {container_id[:12]!r}: {exc}") from exc

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove a container (must be stopped unless ``force=True``).

        Args:
            container_id: Full Docker container ID.
            force: Kill and remove even if running.

        Raises:
            SandboxError: On unexpected Docker error.
        """
        log.info(
            "sandbox.manager.remove",
            container_id=container_id[:12],
            force=force,
        )
        try:
            container = self._docker.containers.container(container_id)
            await container.delete(force=force)
            log.info("sandbox.manager.removed", container_id=container_id[:12])
        except Exception as exc:
            raise SandboxError(f"Failed to remove container {container_id[:12]!r}: {exc}") from exc

    # ── Inspection ────────────────────────────────────────────────────────────

    async def get_status(self, container_id: str) -> ContainerStatus:
        """Return the current lifecycle status of a container.

        Args:
            container_id: Full Docker container ID.

        Returns:
            A ``ContainerStatus`` enum value.

        Raises:
            SandboxError: If Docker returns an unexpected error.
        """
        try:
            container = self._docker.containers.container(container_id)
            info = await container.show()
            state = info.get("State", {}).get("Status", "")
            _status_map = {
                "created": ContainerStatus.CREATED,
                "running": ContainerStatus.RUNNING,
                "exited": ContainerStatus.STOPPED,
                "dead": ContainerStatus.ERROR,
                "removing": ContainerStatus.REMOVED,
            }
            return _status_map.get(state, ContainerStatus.ERROR)
        except Exception as exc:
            raise SandboxError(f"Failed to get status for {container_id[:12]!r}: {exc}") from exc

    async def health_check(
        self,
        container_id: str,
        retries: int = _HEALTH_CHECK_RETRIES,
    ) -> bool:
        """Poll container state until RUNNING or max retries exceeded.

        Args:
            container_id: Full Docker container ID.
            retries: Number of polling attempts before raising.

        Returns:
            ``True`` when the container is running.

        Raises:
            ContainerHealthCheckError: If not running after all retries.
        """
        for attempt in range(retries):
            status = await self.get_status(container_id)
            if status == ContainerStatus.RUNNING:
                log.debug(
                    "sandbox.manager.healthy",
                    container_id=container_id[:12],
                    attempt=attempt,
                )
                return True
            if status in (ContainerStatus.STOPPED, ContainerStatus.REMOVED, ContainerStatus.ERROR):
                raise ContainerHealthCheckError(
                    f"Container {container_id[:12]!r} is in terminal state {status}"
                )
            await asyncio.sleep(_HEALTH_CHECK_INTERVAL)

        raise ContainerHealthCheckError(
            f"Container {container_id[:12]!r} not healthy after {retries} retries"
        )

    # ── Bulk operations ───────────────────────────────────────────────────────

    async def cleanup_all(self) -> int:
        """Stop and remove all Seraph-managed containers.

        Returns:
            Number of containers cleaned up.

        Raises:
            SandboxError: If Docker cannot list containers.
        """
        log.info("sandbox.manager.cleanup_all")
        try:
            containers = await self._docker.containers.list(
                all=True,
                filters={"label": [f"{_LABEL_MANAGED}=true"]},
            )
            count = 0
            for container in containers:
                try:
                    await container.delete(force=True)
                    count += 1
                except Exception as exc:
                    log.warning(
                        "sandbox.manager.cleanup_skip",
                        error=str(exc),
                    )
            log.info("sandbox.manager.cleaned_up", count=count)
            return count
        except Exception as exc:
            raise SandboxError(f"cleanup_all failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying Docker client connection."""
        try:
            await self._docker.close()
        except Exception:
            pass
