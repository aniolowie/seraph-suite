"""Health check routes: GET /api/health and GET /api/readyz."""

from __future__ import annotations

import redis.asyncio
import structlog
from fastapi import APIRouter
from neo4j import AsyncGraphDatabase

from seraph.api.deps import QdrantClientDep, SettingsDep
from seraph.api.schemas import HealthResponse, ServiceStatus

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Basic liveness probe")
async def health() -> HealthResponse:
    """Return ``{"status": "ok"}`` — lightweight liveness check."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse, summary="Readiness probe")
async def readyz(
    cfg: SettingsDep,
    qdrant: QdrantClientDep,
) -> HealthResponse:
    """Check connectivity to Qdrant, Neo4j, and Redis.

    Returns HTTP 200 even when degraded so orchestrators can read the body.
    """
    services: list[ServiceStatus] = []

    # ── Qdrant ────────────────────────────────────────────────────────────────
    try:
        await qdrant.get_collections()
        services.append(ServiceStatus(name="qdrant", ok=True))
    except Exception as exc:
        log.warning("readyz.qdrant_fail", error=str(exc))
        services.append(ServiceStatus(name="qdrant", ok=False, detail=str(exc)))

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        r = redis.asyncio.from_url(cfg.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        services.append(ServiceStatus(name="redis", ok=True))
    except Exception as exc:
        log.warning("readyz.redis_fail", error=str(exc))
        services.append(ServiceStatus(name="redis", ok=False, detail=str(exc)))

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    try:
        driver = AsyncGraphDatabase.driver(
            cfg.neo4j_uri,
            auth=(cfg.neo4j_user, cfg.neo4j_password),
        )
        await driver.verify_connectivity()
        await driver.close()
        services.append(ServiceStatus(name="neo4j", ok=True))
    except Exception as exc:
        log.warning("readyz.neo4j_fail", error=str(exc))
        services.append(ServiceStatus(name="neo4j", ok=False, detail=str(exc)))

    overall = "ok" if all(s.ok for s in services) else "degraded"
    return HealthResponse(status=overall, services=services)
