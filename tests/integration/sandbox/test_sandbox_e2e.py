"""End-to-end sandbox integration tests.

These tests require a live Docker daemon.  They are skipped automatically
when Docker is unavailable.  Run explicitly with::

    pytest tests/integration/sandbox/ -m integration -v
"""

from __future__ import annotations

import pytest


def _docker_available() -> bool:
    try:
        import subprocess

        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.integration
skip_no_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon not available",
)


@skip_no_docker
@pytest.mark.asyncio
async def test_container_lifecycle() -> None:
    """Create, start, exec, stop, remove a real container."""
    import aiodocker

    from seraph.sandbox.executor import SandboxExecutor
    from seraph.sandbox.manager import ContainerManager
    from seraph.sandbox.models import ContainerSpec, ContainerStatus

    async with aiodocker.Docker() as docker:
        mgr = ContainerManager(docker)
        executor = SandboxExecutor(docker)

        spec = ContainerSpec(
            agent_name="integration-test",
            image="alpine:latest",
            cpu_limit=0.5,
            memory_limit_mb=128,
        )
        info = await mgr.create_container(spec)
        try:
            started = await mgr.start_container(info.container_id)
            assert started.status == ContainerStatus.RUNNING

            result = await executor.execute_command(
                info.container_id,
                ["echo", "seraph-test"],
                workdir="/tmp",
            )
            assert result.exit_code == 0
            assert "seraph-test" in result.stdout

            await mgr.stop_container(info.container_id)
        finally:
            await mgr.remove_container(info.container_id, force=True)


@skip_no_docker
@pytest.mark.asyncio
async def test_network_create_remove() -> None:
    """Create and remove a Seraph network."""
    import aiodocker

    from seraph.sandbox.network import SandboxNetworkManager

    async with aiodocker.Docker() as docker:
        net_mgr = SandboxNetworkManager(docker)
        nid = await net_mgr.create_engagement_network("seraph-integ-test-net")
        assert nid

        # Idempotent — second call returns same ID.
        nid2 = await net_mgr.create_engagement_network("seraph-integ-test-net")
        assert nid2 == nid

        await net_mgr.remove_network("seraph-integ-test-net")


@skip_no_docker
@pytest.mark.asyncio
async def test_pool_lease_release() -> None:
    """Pool initialises, leases, and releases a real container."""
    import aiodocker

    from seraph.sandbox.manager import ContainerManager
    from seraph.sandbox.models import ContainerSpec
    from seraph.sandbox.pool import ContainerPool

    async with aiodocker.Docker() as docker:
        mgr = ContainerManager(docker)
        spec = ContainerSpec(
            agent_name="pool-integ",
            image="alpine:latest",
            cpu_limit=0.25,
            memory_limit_mb=64,
        )
        pool = ContainerPool(manager=mgr, pool_size=1, timeout_seconds=10, base_spec=spec)
        try:
            await pool.initialize()
            cid = await pool.lease("integ-agent")
            assert cid
            await pool.release(cid)
        finally:
            await pool.shutdown()
