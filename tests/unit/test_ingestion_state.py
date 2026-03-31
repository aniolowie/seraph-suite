"""Unit tests for IngestionStateDB."""

from __future__ import annotations

from pathlib import Path

import pytest

from seraph.ingestion.models import IngestionRecord
from seraph.ingestion.state import IngestionStateDB


@pytest.fixture
async def db(tmp_path: Path) -> IngestionStateDB:
    """Create a fresh IngestionStateDB with a temp file."""
    state = IngestionStateDB(db_path=tmp_path / "test_state.db")
    await state.init_db()
    return state


class TestIngestionStateDB:
    async def test_init_db_is_idempotent(self, tmp_path: Path) -> None:
        state = IngestionStateDB(db_path=tmp_path / "db.sqlite")
        await state.init_db()
        await state.init_db()  # second call must not raise

    async def test_new_id_is_not_ingested(self, db: IngestionStateDB) -> None:
        assert not await db.is_ingested("CVE-2021-44228", "nvd")

    async def test_mark_ingested_then_is_ingested(self, db: IngestionStateDB) -> None:
        record = IngestionRecord(source_id="CVE-2021-44228", source="nvd", chunk_count=1)
        await db.mark_ingested(record)
        assert await db.is_ingested("CVE-2021-44228", "nvd")

    async def test_mark_ingested_twice_does_not_error(self, db: IngestionStateDB) -> None:
        record = IngestionRecord(source_id="CVE-2021-44228", source="nvd", chunk_count=1)
        await db.mark_ingested(record)
        await db.mark_ingested(record)  # idempotent

    async def test_failed_record_not_counted_as_ingested(self, db: IngestionStateDB) -> None:
        await db.mark_failed("CVE-2021-44228", "nvd", "network error")
        assert not await db.is_ingested("CVE-2021-44228", "nvd")

    async def test_different_sources_are_independent(self, db: IngestionStateDB) -> None:
        record = IngestionRecord(source_id="12345", source="nvd", chunk_count=1)
        await db.mark_ingested(record)
        assert not await db.is_ingested("12345", "exploitdb")

    async def test_get_stats(self, db: IngestionStateDB) -> None:
        for i in range(3):
            await db.mark_ingested(
                IngestionRecord(source_id=f"CVE-{i}", source="nvd", chunk_count=1)
            )
        await db.mark_failed("CVE-fail", "nvd", "error")
        stats = await db.get_stats("nvd")
        assert stats.get("ok", 0) == 3
        assert stats.get("failed", 0) == 1

    async def test_clear_source(self, db: IngestionStateDB) -> None:
        await db.mark_ingested(IngestionRecord(source_id="CVE-001", source="nvd", chunk_count=1))
        await db.clear_source("nvd")
        assert not await db.is_ingested("CVE-001", "nvd")

    async def test_clear_source_does_not_affect_other_sources(self, db: IngestionStateDB) -> None:
        await db.mark_ingested(IngestionRecord(source_id="1", source="nvd", chunk_count=1))
        await db.mark_ingested(IngestionRecord(source_id="2", source="exploitdb", chunk_count=1))
        await db.clear_source("nvd")
        assert await db.is_ingested("2", "exploitdb")

    async def test_stats_empty_source(self, db: IngestionStateDB) -> None:
        stats = await db.get_stats("nonexistent")
        assert stats == {}
