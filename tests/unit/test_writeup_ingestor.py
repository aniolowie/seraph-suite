"""Unit tests for WriteupIngestor (6 tests)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.ingestion.writeups import WriteupIngestor, _parse_frontmatter, _strip_frontmatter


def _make_ingestor(tmp_path: Path) -> WriteupIngestor:
    """Build a WriteupIngestor with mock dependencies."""
    dense = MagicMock()
    dense.embed_texts = AsyncMock(return_value=[[0.1] * 768])
    sparse = MagicMock()
    sparse.embed_texts = AsyncMock(return_value=[MagicMock()])
    store = MagicMock()
    store.upsert_chunks = AsyncMock()
    state = MagicMock()
    state.is_ingested = AsyncMock(return_value=False)
    state.mark_ingested = AsyncMock()
    return WriteupIngestor(
        dense_embedder=dense,
        sparse_embedder=sparse,
        vector_store=store,
        state_db=state,
    )


def test_parse_frontmatter_extracts_fields():
    """_parse_frontmatter returns dict from YAML frontmatter."""
    content = "---\ntitle: HTB Lame\nsource: htb\ndifficulty: easy\n---\n# Body"
    meta = _parse_frontmatter(content)
    assert meta["title"] == "HTB Lame"
    assert meta["source"] == "htb"
    assert meta["difficulty"] == "easy"


def test_parse_frontmatter_returns_empty_on_missing():
    """_parse_frontmatter returns empty dict when no frontmatter."""
    assert _parse_frontmatter("# Just a header\nSome text.") == {}


def test_strip_frontmatter_removes_yaml_block():
    """_strip_frontmatter removes the YAML block leaving only body."""
    content = "---\ntitle: test\n---\n# Body\nContent here."
    body = _strip_frontmatter(content)
    assert "---" not in body
    assert "Body" in body


@pytest.mark.asyncio
async def test_ingest_empty_dir_returns_zero(tmp_path):
    """ingest returns 0 when the writeups dir is empty."""
    ingestor = _make_ingestor(tmp_path)
    count = await ingestor.ingest(writeups_dir=tmp_path)
    assert count == 0


@pytest.mark.asyncio
async def test_ingest_skips_missing_dir(tmp_path):
    """ingest returns 0 when the writeups dir doesn't exist."""
    ingestor = _make_ingestor(tmp_path)
    count = await ingestor.ingest(writeups_dir=tmp_path / "nonexistent")
    assert count == 0


@pytest.mark.asyncio
async def test_ingest_processes_markdown_file(tmp_path):
    """ingest ingests a markdown file and returns positive chunk count."""
    md_file = tmp_path / "htb_lame.md"
    md_file.write_text(
        "---\ntitle: HTB Lame\nsource: htb\n---\n"
        "# HTB Lame Writeup\n\n"
        "This machine uses Samba 3.0.20 which is vulnerable to CVE-2007-2447.\n"
        "Use Metasploit module exploit/multi/samba/usermap_script to get a shell.\n",
        encoding="utf-8",
    )
    ingestor = _make_ingestor(tmp_path)
    # Patch embed_texts to return correct number of vectors
    ingestor._dense.embed_texts = AsyncMock(side_effect=lambda texts: [[0.1] * 768] * len(texts))
    ingestor._sparse.embed_texts = AsyncMock(side_effect=lambda texts: [MagicMock()] * len(texts))

    count = await ingestor.ingest(writeups_dir=tmp_path)
    assert count > 0
    ingestor._store.upsert_chunks.assert_called_once()
