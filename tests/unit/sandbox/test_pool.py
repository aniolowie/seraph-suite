"""Unit tests for ContainerPool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.exceptions import ContainerPoolExhaustedError
from seraph.sandbox.manager import ContainerManager
from seraph.sandbox.models import ContainerSpec, ContainerStatus
from seraph.sandbox.pool import ContainerPool


@pytest.fixture()
def mock_manager() -> MagicMock:
    mgr = MagicMock(spec=ContainerManager)
    return mgr


@pytest.fixture()
def spec() -> ContainerSpec:
    return ContainerSpec(agent_name="pool", image="seraph-agent:latest", network_name="")


@pytest.fixture()
def pool(mock_manager: MagicMock, spec: ContainerSpec) -> ContainerPool:
    return ContainerPool(
        manager=mock_manager,
        pool_size=2,
        timeout_seconds=1,
        base_spec=spec,
    )


def _setup_manager_for_pool(mock_manager: MagicMock, container_ids: list[str]) -> None:
    """Wire up mock manager to return container IDs in sequence."""
    from seraph.sandbox.models import ContainerInfo

    infos = [
        ContainerInfo(
            container_id=cid,
            agent_name="pool",
            status=ContainerStatus.CREATED,
            spec=ContainerSpec(agent_name="pool", image="img"),
        )
        for cid in container_ids
    ]
    mock_manager.create_container = AsyncMock(side_effect=infos)
    mock_manager.start_container = AsyncMock()
    mock_manager.health_check = AsyncMock(return_value=True)
    mock_manager.get_status = AsyncMock(return_value=ContainerStatus.RUNNING)


@pytest.mark.asyncio
async def test_initialize_creates_containers(pool: ContainerPool, mock_manager: MagicMock) -> None:
    """Pool creates pool_size containers on initialize."""
    _setup_manager_for_pool(mock_manager, ["c1", "c2"])
    await pool.initialize()
    assert mock_manager.create_container.call_count == 2
    assert pool._available.qsize() == 2


@pytest.mark.asyncio
async def test_initialize_idempotent(pool: ContainerPool, mock_manager: MagicMock) -> None:
    """Calling initialize twice is a no-op."""
    _setup_manager_for_pool(mock_manager, ["c1", "c2"])
    await pool.initialize()
    await pool.initialize()
    assert mock_manager.create_container.call_count == 2


@pytest.mark.asyncio
async def test_lease_returns_container_id(pool: ContainerPool, mock_manager: MagicMock) -> None:
    _setup_manager_for_pool(mock_manager, ["c1", "c2"])
    await pool.initialize()
    cid = await pool.lease("recon")
    assert cid in ("c1", "c2")
    assert pool._available.qsize() == 1


@pytest.mark.asyncio
async def test_release_puts_back(pool: ContainerPool, mock_manager: MagicMock) -> None:
    _setup_manager_for_pool(mock_manager, ["c1", "c2"])
    await pool.initialize()
    cid = await pool.lease("recon")
    assert pool._available.qsize() == 1
    await pool.release(cid)
    assert pool._available.qsize() == 2


@pytest.mark.asyncio
async def test_lease_exhausted_raises(pool: ContainerPool, mock_manager: MagicMock) -> None:
    """ContainerPoolExhaustedError when all containers are leased."""
    _setup_manager_for_pool(mock_manager, ["c1", "c2"])
    await pool.initialize()
    await pool.lease("agent1")
    await pool.lease("agent2")
    with pytest.raises(ContainerPoolExhaustedError):
        await pool.lease("agent3")


@pytest.mark.asyncio
async def test_dead_container_replaced_on_lease(
    pool: ContainerPool, mock_manager: MagicMock
) -> None:
    """Dead containers are replaced transparently during lease."""
    from seraph.sandbox.models import ContainerInfo

    # First call returns dead container, second returns replacement.
    mock_manager.create_container = AsyncMock(
        side_effect=[
            ContainerInfo(
                container_id="dead1",
                agent_name="pool",
                status=ContainerStatus.CREATED,
                spec=ContainerSpec(agent_name="pool", image="img"),
            ),
            ContainerInfo(
                container_id="c2",
                agent_name="pool",
                status=ContainerStatus.CREATED,
                spec=ContainerSpec(agent_name="pool", image="img"),
            ),
            ContainerInfo(
                container_id="fresh1",
                agent_name="pool",
                status=ContainerStatus.CREATED,
                spec=ContainerSpec(agent_name="pool", image="img"),
            ),
        ]
    )
    mock_manager.start_container = AsyncMock()
    mock_manager.health_check = AsyncMock(return_value=True)
    mock_manager.remove_container = AsyncMock()

    # First get_status call (for "dead1") returns STOPPED, rest RUNNING.
    statuses = [ContainerStatus.STOPPED, ContainerStatus.RUNNING, ContainerStatus.RUNNING]
    mock_manager.get_status = AsyncMock(side_effect=statuses)

    pool._pool_size = 2
    await pool.initialize()
    cid = await pool.lease("recon")
    assert cid == "fresh1"
