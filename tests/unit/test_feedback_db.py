"""Unit tests for FeedbackDB (6 tests)."""

from __future__ import annotations

import pytest

from seraph.learning.feedback import FeedbackDB


@pytest.fixture
async def db(tmp_path):
    """FeedbackDB backed by a temporary SQLite file."""
    db_path = tmp_path / "test_feedback.db"
    feedback = FeedbackDB(db_path=db_path)
    await feedback.initialize_schema()
    return feedback


@pytest.mark.asyncio
async def test_initialize_schema_is_idempotent(tmp_path):
    """initialize_schema can be called multiple times without error."""
    db_path = tmp_path / "idem.db"
    db = FeedbackDB(db_path=db_path)
    await db.initialize_schema()
    await db.initialize_schema()  # second call must not raise


@pytest.mark.asyncio
async def test_log_retrieval_returns_record_id(db):
    """log_retrieval returns a non-empty string record ID."""
    record_id = await db.log_retrieval(
        engagement_id="eng-001",
        agent_name="recon",
        query="nmap samba vulnerability",
        retrieved_doc_ids=["doc-a", "doc-b", "doc-c"],
    )
    assert isinstance(record_id, str)
    assert len(record_id) > 0


@pytest.mark.asyncio
async def test_mark_citations_updates_cited_flag(db):
    """mark_citations marks the correct doc IDs as cited."""
    record_id = await db.log_retrieval(
        engagement_id="eng-002",
        agent_name="exploit",
        query="samba ms-rpc exploit",
        retrieved_doc_ids=["doc-1", "doc-2", "doc-3"],
    )
    await db.mark_citations(record_id, cited_doc_ids=["doc-1", "doc-3"])

    record = await db.get_record(record_id)
    assert record is not None
    assert set(record.cited_doc_ids) == {"doc-1", "doc-3"}
    assert "doc-2" not in record.cited_doc_ids


@pytest.mark.asyncio
async def test_get_uncited_doc_ids(db):
    """get_uncited_doc_ids returns only uncited doc refs."""
    record_id = await db.log_retrieval(
        engagement_id="eng-003",
        agent_name="recon",
        query="ftp anonymous login",
        retrieved_doc_ids=["doc-x", "doc-y", "doc-z"],
    )
    await db.mark_citations(record_id, cited_doc_ids=["doc-x"])

    uncited = await db.get_uncited_doc_ids()
    uncited_ids = [row["doc_id"] for row in uncited]
    assert "doc-y" in uncited_ids
    assert "doc-z" in uncited_ids
    assert "doc-x" not in uncited_ids


@pytest.mark.asyncio
async def test_save_and_retrieve_triplet(db):
    """save_triplet persists a triplet retrievable via get_pending_triplets."""
    await db.save_triplet(
        query="SMB exploit",
        positive_doc_id="pos-1",
        negative_doc_id="neg-1",
        positive_text="Samba remote code execution via ms17-010",
        negative_text="Apache HTTP server directory listing",
        source="feedback",
    )

    pending = await db.get_pending_triplets()
    assert len(pending) == 1
    assert pending[0]["positive_doc_id"] == "pos-1"
    assert pending[0]["used_in_training"] == 0


@pytest.mark.asyncio
async def test_mark_triplets_used(db):
    """mark_triplets_used moves triplets out of the pending set."""
    await db.save_triplet(
        query="privesc sudo exploit",
        positive_doc_id="pos-2",
        negative_doc_id="neg-2",
        positive_text="sudo buffer overflow CVE-2021-3156",
        negative_text="Windows print spooler vulnerability",
        source="feedback",
    )
    pending_before = await db.get_pending_triplets()
    assert len(pending_before) == 1

    triplet_id = pending_before[0]["id"]
    await db.mark_triplets_used([triplet_id])

    pending_after = await db.get_pending_triplets()
    assert len(pending_after) == 0

    stats = await db.get_stats()
    assert stats["used_triplets"] == 1
    assert stats["pending_triplets"] == 0
