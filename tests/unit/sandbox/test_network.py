"""Unit tests for SandboxNetworkManager (all Docker calls mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.exceptions import NetworkSetupError
from seraph.sandbox.network import SandboxNetworkManager


@pytest.fixture()
def mock_docker() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mgr(mock_docker: MagicMock) -> SandboxNetworkManager:
    return SandboxNetworkManager(docker_client=mock_docker)


@pytest.mark.asyncio
async def test_create_network_new(mgr: SandboxNetworkManager, mock_docker: MagicMock) -> None:
    """Creates a new network when none exists."""
    mock_docker.networks.list = AsyncMock(return_value=[])
    fake_network = MagicMock()
    fake_network.show = AsyncMock(return_value={"Id": "netid123abc"})
    mock_docker.networks.create = AsyncMock(return_value=fake_network)

    nid = await mgr.create_engagement_network("seraph-test-net", "10.10.10.1")
    assert nid == "netid123abc"
    mock_docker.networks.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_network_idempotent(
    mgr: SandboxNetworkManager, mock_docker: MagicMock
) -> None:
    """Returns existing network ID without creating a duplicate."""
    existing_net = MagicMock()
    existing_net.show = AsyncMock(return_value={"Id": "existingid", "Name": "seraph-test-net"})
    mock_docker.networks.list = AsyncMock(return_value=[existing_net])

    nid = await mgr.create_engagement_network("seraph-test-net")
    assert nid == "existingid"


@pytest.mark.asyncio
async def test_remove_network(mgr: SandboxNetworkManager, mock_docker: MagicMock) -> None:
    """Removes a network that exists."""
    fake_net = MagicMock()
    fake_net.show = AsyncMock(return_value={"Id": "nid", "Name": "seraph-test-net"})
    fake_net.delete = AsyncMock()
    mock_docker.networks.list = AsyncMock(return_value=[fake_net])

    await mgr.remove_network("seraph-test-net")
    fake_net.delete.assert_called_once()


@pytest.mark.asyncio
async def test_create_network_error_raises(
    mgr: SandboxNetworkManager, mock_docker: MagicMock
) -> None:
    """Docker errors are wrapped as NetworkSetupError."""
    mock_docker.networks.list = AsyncMock(side_effect=RuntimeError("docker down"))

    with pytest.raises(NetworkSetupError, match="docker down"):
        await mgr.create_engagement_network("fail-net")
