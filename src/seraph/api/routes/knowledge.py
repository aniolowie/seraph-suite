"""Knowledge base stats routes.

GET /api/knowledge/stats       — Qdrant collection info + ingestion status
GET /api/knowledge/ingestion   — per-source ingestion status only
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from seraph.api.deps import QdrantClientDep, SettingsDep
from seraph.api.schemas import (
    CollectionStats,
    IngestionSourceStatus,
    KnowledgeStatsResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_KNOWN_SOURCES = ("nvd", "exploitdb", "mitre", "writeups", "ctftime")


async def _get_collection_stats(qdrant: object, collection_name: str) -> CollectionStats:
    """Fetch Qdrant collection metadata.

    Args:
        qdrant: AsyncQdrantClient instance.
        collection_name: Name of the collection to inspect.

    Returns:
        Populated CollectionStats.
    """
    try:
        info = await qdrant.get_collection(collection_name)  # type: ignore[attr-defined]
        status = str(getattr(info, "status", "unknown"))
        points = int(getattr(info, "points_count", 0) or 0)
        vectors = int(
            getattr(getattr(info, "vectors_count", None), "__len__", lambda: points)()
            if hasattr(getattr(info, "vectors_count", None), "__len__")
            else (getattr(info, "vectors_count", points) or points)
        )
        indexed = status.lower() in ("green", "ok")
        return CollectionStats(
            collection_name=collection_name,
            points_count=points,
            vectors_count=vectors,
            indexed=indexed,
            status=status,
        )
    except Exception as exc:
        log.warning("knowledge.collection_stats_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"Qdrant unavailable: {exc}") from exc


async def _get_ingestion_status(db_path: object) -> list[IngestionSourceStatus]:
    """Query the SQLite ingestion state for each known source.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        List of IngestionSourceStatus, one per source.
    """
    from pathlib import Path

    import aiosqlite

    results: list[IngestionSourceStatus] = []
    path = Path(str(db_path))

    if not path.exists():
        return [
            IngestionSourceStatus(source=s, document_count=0, last_updated=None)
            for s in _KNOWN_SOURCES
        ]

    try:
        async with aiosqlite.connect(path) as conn:
            for source in _KNOWN_SOURCES:
                async with conn.execute(
                    """
                    SELECT COUNT(*), MAX(ingested_at)
                    FROM ingestion_records
                    WHERE source = ? AND status = 'ingested'
                    """,
                    (source,),
                ) as cursor:
                    row = await cursor.fetchone()
                    count = int(row[0]) if row and row[0] else 0
                    last_updated = row[1] if row and row[1] else None
                    if last_updated and isinstance(last_updated, str):
                        from datetime import datetime

                        try:
                            last_updated = datetime.fromisoformat(last_updated)
                        except ValueError:
                            last_updated = None

                async with conn.execute(
                    "SELECT COUNT(*) FROM ingestion_records WHERE source = ? AND status = 'failed'",
                    (source,),
                ) as cursor:
                    err_row = await cursor.fetchone()
                    errors = int(err_row[0]) if err_row and err_row[0] else 0

                results.append(
                    IngestionSourceStatus(
                        source=source,
                        document_count=count,
                        last_updated=last_updated,
                        errors=errors,
                    )
                )
    except Exception as exc:
        log.warning("knowledge.ingestion_status_failed", error=str(exc))
        return [
            IngestionSourceStatus(source=s, document_count=0, last_updated=None)
            for s in _KNOWN_SOURCES
        ]

    return results


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=KnowledgeStatsResponse, summary="KB stats")
async def knowledge_stats(
    cfg: SettingsDep,
    qdrant: QdrantClientDep,
) -> KnowledgeStatsResponse:
    """Return Qdrant collection info combined with per-source ingestion status."""
    collection = await _get_collection_stats(qdrant, cfg.qdrant_collection_name)
    ingestion = await _get_ingestion_status(cfg.sqlite_db_path)
    return KnowledgeStatsResponse(collection=collection, ingestion=ingestion)


@router.get(
    "/ingestion",
    response_model=list[IngestionSourceStatus],
    summary="Ingestion status",
)
async def ingestion_status(cfg: SettingsDep) -> list[IngestionSourceStatus]:
    """Return per-source ingestion status from the SQLite state database."""
    return await _get_ingestion_status(cfg.sqlite_db_path)
