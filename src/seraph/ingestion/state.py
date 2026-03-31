"""SQLite-backed ingestion state tracker for idempotency.

Ensures that already-ingested documents are skipped on re-runs.
Uses aiosqlite with WAL journal mode to support concurrent Celery workers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiosqlite
import structlog

from seraph.config import settings
from seraph.exceptions import IngestionError
from seraph.ingestion.models import IngestionRecord

log = structlog.get_logger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingestion_records (
    source_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'ok',
    error       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source_id, source)
)
"""


class IngestionStateDB:
    """Async SQLite tracker for ingestion idempotency.

    Create one instance per process. The DB file is created automatically
    on first :meth:`init_db` call. All methods are async.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialise without opening a connection.

        Args:
            db_path: Path to the SQLite file. Defaults to ``settings.sqlite_db_path``.
        """
        self._db_path = db_path or settings.sqlite_db_path

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        """Open a connection with WAL mode and close it on exit."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self._db_path)) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            yield conn

    async def init_db(self) -> None:
        """Create the ingestion_records table if it does not exist.

        Safe to call multiple times (idempotent).

        Raises:
            IngestionError: On DB creation failure.
        """
        try:
            async with self._connect() as conn:
                await conn.execute(_CREATE_TABLE_SQL)
                await conn.commit()
            log.debug("ingestion_state.db_ready", path=str(self._db_path))
        except Exception as exc:
            raise IngestionError(f"Failed to initialise ingestion DB: {exc}") from exc

    async def is_ingested(self, source_id: str, source: str) -> bool:
        """Check whether a document has already been successfully ingested.

        Args:
            source_id: Document ID in the source system (e.g. ``"CVE-2021-44228"``).
            source: Source name (e.g. ``"nvd"``).

        Returns:
            ``True`` if a record exists with ``status='ok'``.

        Raises:
            IngestionError: On DB query failure.
        """
        try:
            async with self._connect() as conn:
                cursor = await conn.execute(
                    "SELECT 1 FROM ingestion_records "
                    "WHERE source_id = ? AND source = ? AND status = 'ok'",
                    (source_id, source),
                )
                row = await cursor.fetchone()
                return row is not None
        except Exception as exc:
            raise IngestionError(f"Failed to check ingestion state: {exc}") from exc

    async def mark_ingested(self, record: IngestionRecord) -> None:
        """Insert or replace an ingestion record with ``status='ok'``.

        Args:
            record: Completed ingestion record.

        Raises:
            IngestionError: On DB write failure.
        """
        try:
            async with self._connect() as conn:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO ingestion_records
                        (source_id, source, ingested_at, chunk_count, status, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.source_id,
                        record.source,
                        record.ingested_at.isoformat(),
                        record.chunk_count,
                        record.status,
                        record.error,
                    ),
                )
                await conn.commit()
        except Exception as exc:
            raise IngestionError(f"Failed to mark ingested: {exc}") from exc

    async def mark_failed(self, source_id: str, source: str, error: str) -> None:
        """Record a failed ingestion attempt.

        Args:
            source_id: Document ID.
            source: Source name.
            error: Error description.

        Raises:
            IngestionError: On DB write failure.
        """
        record = IngestionRecord(
            source_id=source_id,
            source=source,
            ingested_at=datetime.utcnow(),
            chunk_count=0,
            status="failed",
            error=error[:500],  # cap error length
        )
        await self.mark_ingested(record)

    async def get_stats(self, source: str) -> dict[str, int]:
        """Return ingestion counts by status for a given source.

        Args:
            source: Source name (e.g. ``"nvd"``).

        Returns:
            Dict mapping status → count, e.g. ``{"ok": 1000, "failed": 5}``.

        Raises:
            IngestionError: On DB query failure.
        """
        try:
            async with self._connect() as conn:
                cursor = await conn.execute(
                    "SELECT status, COUNT(*) FROM ingestion_records "
                    "WHERE source = ? GROUP BY status",
                    (source,),
                )
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
        except Exception as exc:
            raise IngestionError(f"Failed to get stats: {exc}") from exc

    async def clear_source(self, source: str) -> None:
        """Delete all ingestion records for a source (enables re-ingestion).

        Args:
            source: Source name to clear.

        Raises:
            IngestionError: On DB delete failure.
        """
        try:
            async with self._connect() as conn:
                await conn.execute(
                    "DELETE FROM ingestion_records WHERE source = ?",
                    (source,),
                )
                await conn.commit()
            log.info("ingestion_state.cleared", source=source)
        except Exception as exc:
            raise IngestionError(f"Failed to clear source: {exc}") from exc
