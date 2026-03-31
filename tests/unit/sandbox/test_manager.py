"""Unit tests for ContainerManager (all Docker calls mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.exceptions import ContainerHealthCheckError, ContainerStartError
from seraph.sandbox.manager import ContainerManager
from seraph.sandbox.models import ContainerSpec, ContainerStatus


@pytest.fixture()
def mock_docker() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mgr(mock_docker: MagicMock) -> ContainerManager:
    return ContainerManager(docker_client=mock_docker)


@pytest.fixture()
def spec() -> ContainerSpec:
    return ContainerSpec(agent_name="recon", image="seraph-agent:latest")


@pytest.mark.asyncio
async def test_create_container_success(
    mgr: ContainerManager, mock_docker: MagicMock, spec: ContainerSpec
) -> None:
    fake_container = MagicMock()
    fake_container.id = "abc123def456"
    mock_docker.containers.create = AsyncMock(return_value=fake_container)

    info = await mgr.create_container(spec)
    assert info.container_id == "abc123def456"
    assert info.status == ContainerStatus.CREATED
    assert info.agent_name == "recon"


@pytest.mark.asyncio
async def test_create_container_error_wraps(
    mgr: ContainerManager, mock_docker: MagicMock, spec: ContainerSpec
) -> None:
    mock_docker.containers.create = AsyncMock(side_effect=RuntimeError("image not found"))
    with pytest.raises(ContainerStartError, match="image not found"):
        await mgr.create_container(spec)


@pytest.mark.asyncio
async def test_start_container_success(mgr: ContainerManager, mock_docker: MagicMock) -> None:
    fake_container = MagicMock()
    fake_container.start = AsyncMock()
    fake_container.show = AsyncMock(
        return_value={
            "NetworkSettings": {"Networks": {"bridge": {"IPAddress": "172.17.0.2"}}},
            "Config": {
                "Labels": {"seraph.agent": "recon"},
                "Image": "seraph-agent:latest",
            },
        }
    )
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    info = await mgr.start_container("abc123def456")
    assert info.status == ContainerStatus.RUNNING
    assert info.ip_address == "172.17.0.2"


@pytest.mark.asyncio
async def test_stop_container(mgr: ContainerManager, mock_docker: MagicMock) -> None:
    fake_container = MagicMock()
    fake_container.stop = AsyncMock()
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    await mgr.stop_container("cid123")
    fake_container.stop.assert_called_once_with(t=10)


@pytest.mark.asyncio
async def test_remove_container(mgr: ContainerManager, mock_docker: MagicMock) -> None:
    fake_container = MagicMock()
    fake_container.delete = AsyncMock()
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    await mgr.remove_container("cid123", force=True)
    fake_container.delete.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_get_status_running(mgr: ContainerManager, mock_docker: MagicMock) -> None:
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "running"}})
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    status = await mgr.get_status("cid123")
    assert status == ContainerStatus.RUNNING


@pytest.mark.asyncio
async def test_get_status_exited_maps_to_stopped(
    mgr: ContainerManager, mock_docker: MagicMock
) -> None:
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "exited"}})
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    status = await mgr.get_status("cid123")
    assert status == ContainerStatus.STOPPED


@pytest.mark.asyncio
async def test_health_check_passes_on_running(
    mgr: ContainerManager, mock_docker: MagicMock
) -> None:
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "running"}})
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    result = await mgr.health_check("cid123")
    assert result is True


@pytest.mark.asyncio
async def test_health_check_raises_after_retries(
    mgr: ContainerManager, mock_docker: MagicMock
) -> None:
    fake_container = MagicMock()
    fake_container.show = AsyncMock(return_value={"State": {"Status": "created"}})
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    with patch("seraph.sandbox.manager.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ContainerHealthCheckError):
            await mgr.health_check("cid123", retries=2)
