"""Unit tests for HardNegativeMiner (5 tests)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.learning.negatives import HardNegativeMiner, _bm25_overlap, _token_set


@pytest.fixture
async def feedback_db(tmp_path):
    from seraph.learning.feedback import FeedbackDB

    db = FeedbackDB(db_path=tmp_path / "test.db")
    await db.initialize_schema()
    return db


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.fetch_by_ids = AsyncMock(return_value=[])
    return store


def test_token_set_lowercases_and_splits():
    """_token_set extracts lowercase tokens from text."""
    tokens = _token_set("Apache HTTP Server CVE-2021-44228")
    assert "apache" in tokens
    assert "http" in tokens
    assert "server" in tokens


def test_bm25_overlap_counts_shared_tokens():
    """_bm25_overlap returns the correct shared token count."""
    overlap = _bm25_overlap("samba remote exploit", "samba exploit via ms17-010 remote code")
    assert overlap >= 2  # "samba" and "exploit" and "remote" are shared


@pytest.mark.asyncio
async def test_mine_returns_empty_when_no_uncited(feedback_db, mock_store):
    """mine returns an empty list when there are no uncited doc refs."""
    miner = HardNegativeMiner(feedback_db=feedback_db, vector_store=mock_store)
    triplets = await miner.mine()
    assert triplets == []


@pytest.mark.asyncio
async def test_mine_skips_records_without_citations(feedback_db, mock_store):
    """mine skips feedback records that have no cited docs."""
    await feedback_db.log_retrieval(
        engagement_id="eng-1",
        agent_name="recon",
        query="ftp exploit vulnerability",
        retrieved_doc_ids=["doc-a", "doc-b"],
    )
    # No mark_citations call → no cited docs
    miner = HardNegativeMiner(feedback_db=feedback_db, vector_store=mock_store)
    triplets = await miner.mine()
    assert len(triplets) == 0


@pytest.mark.asyncio
async def test_mine_creates_triplets_when_overlap_sufficient(feedback_db):
    """mine creates triplets when uncited doc has sufficient BM25 overlap."""
    from unittest.mock import AsyncMock, MagicMock

    record_id = await feedback_db.log_retrieval(
        engagement_id="eng-2",
        agent_name="exploit",
        query="samba exploit remote code",
        retrieved_doc_ids=["pos-doc", "neg-doc"],
    )
    await feedback_db.mark_citations(record_id, cited_doc_ids=["pos-doc"])

    # Mock vector store to return text with sufficient overlap
    mock_record = MagicMock()
    mock_record.id = "pos-doc"
    mock_record.payload = {"text": "Samba remote code execution exploit CVE-2007-2447"}

    mock_neg = MagicMock()
    mock_neg.id = "neg-doc"
    mock_neg.payload = {"text": "samba exploit tool for remote code execution targeting"}

    mock_store = MagicMock()
    mock_store.fetch_by_ids = AsyncMock(return_value=[mock_record, mock_neg])

    miner = HardNegativeMiner(
        feedback_db=feedback_db,
        vector_store=mock_store,
        min_overlap=2,
    )
    triplets = await miner.mine(engagement_id="eng-2")
    assert len(triplets) >= 1
    assert triplets[0].positive_doc_id == "pos-doc"
    assert triplets[0].negative_doc_id == "neg-doc"
