"""Docker network management for sandbox isolation.

Each engagement gets its own bridge network scoped to the target IP.
Uses aiodocker for async-native Docker API access.
"""

from __future__ import annotations

import structlog

from seraph.exceptions import NetworkSetupError

log = structlog.get_logger(__name__)

# Label applied to all Seraph-managed networks.
_SERAPH_NETWORK_LABEL = "seraph.managed"


class SandboxNetworkManager:
    """Creates and manages per-engagement Docker bridge networks.

    Each network is named ``seraph-<engagement_id>`` and is scoped to
    a single target IP range.  All containers for the same engagement
    share this network so they can reach the target but not the host.

    Args:
        docker_client: An ``aiodocker.Docker`` instance.
    """

    def __init__(self, docker_client: object) -> None:
        self._docker = docker_client

    async def create_engagement_network(
        self,
        network_name: str,
        target_ip: str = "",
    ) -> str:
        """Create a bridge network for a single engagement.

        If a network with the same name already exists, returns its ID
        without raising an error (idempotent).

        Args:
            network_name: Desired network name (e.g. ``seraph-agent-net``).
            target_ip: Target host IP used as an informational label.

        Returns:
            Docker network ID string.

        Raises:
            NetworkSetupError: If Docker returns an unexpected error.
        """
        log.info(
            "sandbox.network.create",
            network_name=network_name,
            target_ip=target_ip,
        )
        try:
            # Check if it already exists.
            existing = await self._docker.networks.list(filters={"name": [network_name]})
            for net in existing:
                info = await net.show()
                if info["Name"] == network_name:
                    network_id: str = info["Id"]
                    log.info(
                        "sandbox.network.already_exists",
                        network_name=network_name,
                        network_id=network_id[:12],
                    )
                    return network_id

            config: dict[str, object] = {
                "Name": network_name,
                "Driver": "bridge",
                "CheckDuplicate": True,
                "Labels": {
                    _SERAPH_NETWORK_LABEL: "true",
                    "seraph.target_ip": target_ip,
                },
            }
            network = await self._docker.networks.create(config)
            info = await network.show()
            network_id = info["Id"]
            log.info(
                "sandbox.network.created",
                network_name=network_name,
                network_id=network_id[:12],
            )
            return network_id
        except Exception as exc:
            raise NetworkSetupError(f"Failed to create network {network_name!r}: {exc}") from exc

    async def remove_network(self, network_name: str) -> None:
        """Delete a network by name, ignoring not-found errors.

        Args:
            network_name: The Docker network name to remove.

        Raises:
            NetworkSetupError: On unexpected Docker error.
        """
        log.info("sandbox.network.remove", network_name=network_name)
        try:
            networks = await self._docker.networks.list(filters={"name": [network_name]})
            for net in networks:
                info = await net.show()
                if info["Name"] == network_name:
                    await net.delete()
                    log.info("sandbox.network.removed", network_name=network_name)
                    return
            log.debug("sandbox.network.not_found", network_name=network_name)
        except Exception as exc:
            raise NetworkSetupError(f"Failed to remove network {network_name!r}: {exc}") from exc

    async def connect_container(
        self,
        network_name: str,
        container_id: str,
    ) -> None:
        """Attach an existing container to a network.

        Args:
            network_name: Docker network name.
            container_id: Container ID or name.

        Raises:
            NetworkSetupError: If the network or container is not found.
        """
        log.debug(
            "sandbox.network.connect",
            network_name=network_name,
            container_id=container_id[:12],
        )
        try:
            networks = await self._docker.networks.list(filters={"name": [network_name]})
            for net in networks:
                info = await net.show()
                if info["Name"] == network_name:
                    await net.connect({"Container": container_id})
                    return
            raise NetworkSetupError(f"Network {network_name!r} not found when connecting container")
        except NetworkSetupError:
            raise
        except Exception as exc:
            raise NetworkSetupError(
                f"Failed to connect container {container_id[:12]!r} "
                f"to network {network_name!r}: {exc}"
            ) from exc
