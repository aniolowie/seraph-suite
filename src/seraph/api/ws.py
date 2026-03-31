"""WebSocket connection manager for live engagement streaming.

Tracks active WebSocket connections keyed by engagement ID and
broadcasts state-update messages to all subscribers.
"""

from __future__ import annotations

import json
from collections import defaultdict

import structlog
from fastapi import WebSocket

log = structlog.get_logger(__name__)


class ConnectionManager:
    """Manage WebSocket connections grouped by engagement ID.

    Thread-safety note: This implementation is single-process / single-event-loop
    safe (suitable for development).  A Redis pub/sub backend would be needed for
    multi-worker deployments.
    """

    def __init__(self) -> None:
        # engagement_id -> set of connected WebSocket clients
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, engagement_id: str) -> None:
        """Accept a WebSocket and register it for ``engagement_id``.

        Args:
            websocket: The incoming WebSocket connection.
            engagement_id: Engagement to subscribe to.
        """
        await websocket.accept()
        self._connections[engagement_id].add(websocket)
        log.info("ws.connect", engagement_id=engagement_id)

    def disconnect(self, websocket: WebSocket, engagement_id: str) -> None:
        """Deregister a WebSocket from ``engagement_id``.

        Args:
            websocket: The WebSocket that closed.
            engagement_id: Engagement to unsubscribe from.
        """
        self._connections[engagement_id].discard(websocket)
        if not self._connections[engagement_id]:
            del self._connections[engagement_id]
        log.info("ws.disconnect", engagement_id=engagement_id)

    async def broadcast(self, engagement_id: str, data: dict) -> None:
        """Send ``data`` as JSON to all subscribers of ``engagement_id``.

        Dead connections are silently removed.

        Args:
            engagement_id: Target engagement.
            data: Payload to serialize as JSON and send.
        """
        message = json.dumps(data)
        dead: list[WebSocket] = []

        for ws in list(self._connections.get(engagement_id, [])):
            try:
                await ws.send_text(message)
            except Exception as exc:
                log.warning("ws.send_failed", engagement_id=engagement_id, error=str(exc))
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws, engagement_id)

    def active_engagement_ids(self) -> list[str]:
        """Return a list of engagement IDs with at least one subscriber."""
        return list(self._connections.keys())


# Module-level singleton shared across all route handlers.
manager: ConnectionManager = ConnectionManager()
