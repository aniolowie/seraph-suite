"""SQLite-backed feedback database for the self-learning loop.

Every retrieval event is persisted so the hard-negative miner can later
identify which retrieved documents were ignored by the LLM (implicit
negatives).

Uses aiosqlite with WAL journal mode for concurrent read performance.
Schema migrations are handled by ``initialize_schema()`` on startup.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from seraph.config import settings
from seraph.exceptions import FeedbackError
from seraph.learning.models import FeedbackRecord

log = structlog.get_logger(__name__)

_CREATE_FEEDBACK_TABLE = """
CREATE TABLE IF NOT EXISTS feedback_records (
    id            TEXT PRIMARY KEY,
    engagement_id TEXT NOT NULL,
    agent_name    TEXT NOT NULL,
    query         TEXT NOT NULL,
    timestamp     TEXT NOT NULL
);
"""

_CREATE_DOC_REFS_TABLE = """
CREATE TABLE IF NOT EXISTS feedback_doc_refs (
    record_id TEXT NOT NULL REFERENCES feedback_records(id) ON DELETE CASCADE,
    doc_id    TEXT NOT NULL,
    cited     INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_TRIPLETS_TABLE = """
CREATE TABLE IF NOT EXISTS triplets (
    id              TEXT PRIMARY KEY,
    query           TEXT NOT NULL,
    positive_doc_id TEXT NOT NULL,
    negative_doc_id TEXT NOT NULL,
    positive_text   TEXT NOT NULL,
    negative_text   TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'feedback',
    created_at      TEXT NOT NULL,
    used_in_training INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_feedback_engagement ON feedback_records(engagement_id);",
    "CREATE INDEX IF NOT EXISTS idx_doc_refs_record ON feedback_doc_refs(record_id);",
    "CREATE INDEX IF NOT EXISTS idx_triplets_used ON triplets(used_in_training);",
]


class FeedbackDB:
    """Async SQLite store for retrieval feedback and training triplets.

    Args:
        db_path: Path to the SQLite database file. Defaults to settings value.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or settings.sqlite_db_path

    # ── Schema ────────────────────────────────────────────────────────────────

    async def initialize_schema(self) -> None:
        """Create tables and indexes if they don't exist.

        Must be called once before any other method.  Safe to call on every
        startup (idempotent).

        Raises:
            FeedbackError: If the schema migration fails.
        """
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA foreign_keys=ON;")
                await db.execute(_CREATE_FEEDBACK_TABLE)
                await db.execute(_CREATE_DOC_REFS_TABLE)
                await db.execute(_CREATE_TRIPLETS_TABLE)
                for idx_sql in _CREATE_INDEXES:
                    await db.execute(idx_sql)
                await db.commit()
            log.info("feedback_db.schema_initialized", path=str(self._db_path))
        except Exception as exc:
            raise FeedbackError(f"Schema initialization failed: {exc}") from exc

    # ── Write operations ──────────────────────────────────────────────────────

    async def log_retrieval(
        self,
        engagement_id: str,
        agent_name: str,
        query: str,
        retrieved_doc_ids: list[str],
    ) -> str:
        """Log a retrieval event and return the new record ID.

        Args:
            engagement_id: Engagement identifier.
            agent_name: Name of the agent that performed the retrieval.
            query: The query string used for retrieval.
            retrieved_doc_ids: Document IDs returned by the retriever.

        Returns:
            The new ``FeedbackRecord`` ID.

        Raises:
            FeedbackError: On database write failure.
        """
        record_id = str(uuid.uuid4())
        ts = datetime.now(UTC).isoformat()
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("PRAGMA foreign_keys=ON;")
                await db.execute(
                    "INSERT INTO feedback_records (id, engagement_id, agent_name, query, timestamp)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (record_id, engagement_id, agent_name, query, ts),
                )
                if retrieved_doc_ids:
                    await db.executemany(
                        "INSERT INTO feedback_doc_refs (record_id, doc_id, cited) VALUES (?, ?, 0)",
                        [(record_id, doc_id) for doc_id in retrieved_doc_ids],
                    )
                await db.commit()
            log.debug(
                "feedback_db.retrieval_logged",
                record_id=record_id,
                docs=len(retrieved_doc_ids),
            )
            return record_id
        except Exception as exc:
            raise FeedbackError(f"Failed to log retrieval: {exc}") from exc

    async def mark_citations(self, record_id: str, cited_doc_ids: list[str]) -> None:
        """Mark which retrieved documents were actually cited by the LLM.

        Args:
            record_id: ID returned by ``log_retrieval``.
            cited_doc_ids: Document IDs that appeared in the LLM's response.

        Raises:
            FeedbackError: On database write failure.
        """
        if not cited_doc_ids:
            return
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("PRAGMA foreign_keys=ON;")
                await db.executemany(
                    "UPDATE feedback_doc_refs SET cited=1 WHERE record_id=? AND doc_id=?",
                    [(record_id, doc_id) for doc_id in cited_doc_ids],
                )
                await db.commit()
        except Exception as exc:
            raise FeedbackError(f"Failed to mark citations: {exc}") from exc

    async def save_triplet(
        self,
        query: str,
        positive_doc_id: str,
        negative_doc_id: str,
        positive_text: str,
        negative_text: str,
        source: str = "feedback",
    ) -> str:
        """Persist a training triplet.

        Args:
            query: The retrieval query string.
            positive_doc_id: ID of the document cited by the LLM.
            negative_doc_id: ID of the hard-negative document.
            positive_text: Text of the positive document.
            negative_text: Text of the hard-negative document.
            source: Origin label ('feedback' or 'synthetic').

        Returns:
            The new triplet ID.

        Raises:
            FeedbackError: On database write failure.
        """
        triplet_id = str(uuid.uuid4())
        ts = datetime.now(UTC).isoformat()
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO triplets"
                    " (id, query, positive_doc_id, negative_doc_id,"
                    "  positive_text, negative_text, source, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        triplet_id,
                        query,
                        positive_doc_id,
                        negative_doc_id,
                        positive_text,
                        negative_text,
                        source,
                        ts,
                    ),
                )
                await db.commit()
            return triplet_id
        except Exception as exc:
            raise FeedbackError(f"Failed to save triplet: {exc}") from exc

    # ── Read operations ───────────────────────────────────────────────────────

    async def get_uncited_doc_ids(
        self, engagement_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Return retrieved-but-not-cited doc refs for hard negative mining.

        Args:
            engagement_id: Filter to a specific engagement (None = all).
            limit: Maximum rows returned.

        Returns:
            List of dicts with keys: ``record_id``, ``query``, ``doc_id``.

        Raises:
            FeedbackError: On database read failure.
        """
        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                if engagement_id:
                    cursor = await db.execute(
                        "SELECT r.id AS record_id, r.query, d.doc_id"
                        " FROM feedback_records r"
                        " JOIN feedback_doc_refs d ON d.record_id = r.id"
                        " WHERE d.cited = 0 AND r.engagement_id = ?"
                        " LIMIT ?",
                        (engagement_id, limit),
                    )
                else:
                    cursor = await db.execute(
                        "SELECT r.id AS record_id, r.query, d.doc_id"
                        " FROM feedback_records r"
                        " JOIN feedback_doc_refs d ON d.record_id = r.id"
                        " WHERE d.cited = 0"
                        " LIMIT ?",
                        (limit,),
                    )
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as exc:
            raise FeedbackError(f"Failed to fetch uncited docs: {exc}") from exc

    async def get_pending_triplets(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Return triplets not yet used in a training run.

        Args:
            limit: Maximum triplets to return.

        Returns:
            List of triplet dicts.

        Raises:
            FeedbackError: On database read failure.
        """
        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM triplets WHERE used_in_training=0 LIMIT ?",
                    (limit,),
                )
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as exc:
            raise FeedbackError(f"Failed to fetch pending triplets: {exc}") from exc

    async def mark_triplets_used(self, triplet_ids: list[str]) -> None:
        """Mark triplets as consumed by a training run.

        Args:
            triplet_ids: IDs to mark.

        Raises:
            FeedbackError: On database write failure.
        """
        if not triplet_ids:
            return
        placeholders = ",".join("?" * len(triplet_ids))
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    f"UPDATE triplets SET used_in_training=1 WHERE id IN ({placeholders})",
                    triplet_ids,
                )
                await db.commit()
        except Exception as exc:
            raise FeedbackError(f"Failed to mark triplets used: {exc}") from exc

    async def get_stats(self) -> dict[str, int]:
        """Return basic statistics about the feedback database.

        Returns:
            Dict with keys: ``total_records``, ``total_cited``,
            ``total_uncited``, ``pending_triplets``, ``used_triplets``.

        Raises:
            FeedbackError: On database read failure.
        """
        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row

                async def _count(sql: str) -> int:
                    cur = await db.execute(sql)
                    row = await cur.fetchone()
                    return int(row[0]) if row else 0

                return {
                    "total_records": await _count("SELECT COUNT(*) FROM feedback_records"),
                    "total_cited": await _count(
                        "SELECT COUNT(*) FROM feedback_doc_refs WHERE cited=1"
                    ),
                    "total_uncited": await _count(
                        "SELECT COUNT(*) FROM feedback_doc_refs WHERE cited=0"
                    ),
                    "pending_triplets": await _count(
                        "SELECT COUNT(*) FROM triplets WHERE used_in_training=0"
                    ),
                    "used_triplets": await _count(
                        "SELECT COUNT(*) FROM triplets WHERE used_in_training=1"
                    ),
                }
        except Exception as exc:
            raise FeedbackError(f"Failed to get stats: {exc}") from exc

    async def get_record(self, record_id: str) -> FeedbackRecord | None:
        """Fetch a single feedback record by ID.

        Args:
            record_id: Record primary key.

        Returns:
            ``FeedbackRecord`` or ``None`` if not found.

        Raises:
            FeedbackError: On database read failure.
        """
        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT * FROM feedback_records WHERE id=?", (record_id,))
                row = await cur.fetchone()
                if row is None:
                    return None
                cur2 = await db.execute(
                    "SELECT doc_id, cited FROM feedback_doc_refs WHERE record_id=?",
                    (record_id,),
                )
                refs = await cur2.fetchall()
                retrieved = [r["doc_id"] for r in refs]
                cited = [r["doc_id"] for r in refs if r["cited"]]
                return FeedbackRecord(
                    id=row["id"],
                    engagement_id=row["engagement_id"],
                    agent_name=row["agent_name"],
                    query=row["query"],
                    retrieved_doc_ids=retrieved,
                    cited_doc_ids=cited,
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                )
        except Exception as exc:
            raise FeedbackError(f"Failed to fetch record: {exc}") from exc
