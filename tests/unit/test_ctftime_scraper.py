"""Unit tests for CTFTimeScraper (4 tests)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.ingestion.ctftime import CTFTimeScraper, _strip_html


def _make_scraper() -> CTFTimeScraper:
    """Build a CTFTimeScraper with mock dependencies."""
    dense = MagicMock()
    dense.embed_texts = AsyncMock(side_effect=lambda t: [[0.1] * 768] * len(t))
    sparse = MagicMock()
    sparse.embed_texts = AsyncMock(side_effect=lambda t: [MagicMock()] * len(t))
    store = MagicMock()
    store.upsert_chunks = AsyncMock()
    state = MagicMock()
    state.is_ingested = AsyncMock(return_value=False)
    state.mark_ingested = AsyncMock()
    return CTFTimeScraper(
        dense_embedder=dense,
        sparse_embedder=sparse,
        vector_store=store,
        state_db=state,
        rate_limit_sleep=0.0,  # no sleep in tests
    )


def test_strip_html_removes_tags():
    """_strip_html removes HTML tags and normalises whitespace."""
    html = "<html><body><h1>Title</h1><p>Some text here.</p></body></html>"
    result = _strip_html(html)
    assert "<" not in result
    assert "Title" in result
    assert "Some text here." in result


@pytest.mark.asyncio
async def test_ingest_returns_zero_on_api_failure():
    """ingest returns 0 when the CTFTime API returns an error."""
    scraper = _make_scraper()
    with patch.object(scraper, "_fetch_writeup_list", AsyncMock(return_value=[])):
        count = await scraper.ingest(limit=10)
    assert count == 0


@pytest.mark.asyncio
async def test_ingest_skips_entries_without_url():
    """ingest skips entries with empty URL field."""
    scraper = _make_scraper()
    entries = [{"url": "", "title": "no url entry"}]
    with patch.object(scraper, "_fetch_writeup_list", AsyncMock(return_value=entries)):
        count = await scraper.ingest(limit=10)
    assert count == 0


@pytest.mark.asyncio
async def test_ingest_processes_valid_entry():
    """ingest processes a valid entry and returns positive chunk count."""
    scraper = _make_scraper()
    entries = [{"url": "https://example.com/ctf-writeup", "title": "CTF Web Challenge"}]

    html_content = "<html><body>" + ("CTF web challenge writeup. " * 20) + "</body></html>"

    with (
        patch.object(scraper, "_fetch_writeup_list", AsyncMock(return_value=entries)),
        patch.object(scraper, "_fetch_page", AsyncMock(return_value=html_content)),
    ):
        count = await scraper.ingest(limit=1)
    assert count > 0
    scraper._store.upsert_chunks.assert_called_once()
