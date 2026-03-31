"""Engagement monitoring routes.

GET  /api/engagements          — list active engagements
GET  /api/engagements/{id}     — single engagement snapshot
WS   /api/engagements/{id}/ws  — live state stream
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from seraph.api.schemas import EngagementDetail, EngagementSummary
from seraph.api.ws import manager

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/engagements", tags=["engagements"])

# In-memory engagement registry: engagement_id -> state dict.
# Populated by BenchmarkRunner / orchestrator callbacks.
_registry: dict[str, dict[str, Any]] = {}


def register_engagement(engagement_id: str, state: dict[str, Any]) -> None:
    """Register or update an engagement in the in-memory registry.

    Called by BenchmarkRunner and the orchestrator after each state transition.

    Args:
        engagement_id: Unique engagement identifier.
        state: Serialisable snapshot of the engagement state.
    """
    _registry[engagement_id] = state


def unregister_engagement(engagement_id: str) -> None:
    """Remove a completed or failed engagement from the registry.

    Args:
        engagement_id: Engagement to remove.
    """
    _registry.pop(engagement_id, None)


def _to_summary(eid: str, state: dict[str, Any]) -> EngagementSummary:
    started = state.get("started_at") or datetime.now(UTC)
    if isinstance(started, str):
        started = datetime.fromisoformat(started)
    elapsed = time.monotonic() - state.get("_wall_start", time.monotonic())
    return EngagementSummary(
        engagement_id=eid,
        target_ip=state.get("target_ip", ""),
        target_os=state.get("target_os", ""),
        phase=state.get("phase", "unknown"),
        flags_captured=len(state.get("flags", [])),
        findings_count=len(state.get("findings", [])),
        elapsed_seconds=round(elapsed, 1),
        started_at=started,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[EngagementSummary], summary="List active engagements")
async def list_engagements() -> list[EngagementSummary]:
    """Return a summary of every currently registered engagement."""
    return [_to_summary(eid, state) for eid, state in _registry.items()]


@router.get("/{engagement_id}", response_model=EngagementDetail, summary="Engagement snapshot")
async def get_engagement(engagement_id: str) -> EngagementDetail:
    """Return the full state snapshot for a single engagement.

    Args:
        engagement_id: The engagement to retrieve.

    Raises:
        HTTPException: 404 if the engagement is not registered.
    """
    state = _registry.get(engagement_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Engagement '{engagement_id}' not found")

    summary = _to_summary(engagement_id, state)
    return EngagementDetail(
        **summary.model_dump(),
        findings=state.get("findings", []),
        tool_outputs=state.get("tool_outputs", []),
        plan=state.get("plan", []),
    )


@router.websocket("/{engagement_id}/ws")
async def engagement_ws(websocket: WebSocket, engagement_id: str) -> None:
    """WebSocket endpoint for live engagement state updates.

    The client receives a JSON message each time the engagement state changes.
    The first message is the current snapshot (or an empty dict if not started).

    Args:
        websocket: Incoming WebSocket connection.
        engagement_id: Engagement to subscribe to.
    """
    await manager.connect(websocket, engagement_id)
    log.info("ws.engagement.connected", engagement_id=engagement_id)
    try:
        # Send initial snapshot immediately on connect.
        state = _registry.get(engagement_id, {})
        await websocket.send_json({"type": "snapshot", "data": state})

        # Keep connection alive; server pushes updates via manager.broadcast().
        while True:
            await websocket.receive_text()  # heartbeat / keepalive
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, engagement_id)
        log.info("ws.engagement.disconnected", engagement_id=engagement_id)
