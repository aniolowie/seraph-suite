"""CTFTime writeup scraper for ingesting public CTF write-ups.

Scrapes writeup links from the CTFTime API and fetches the linked pages.
Rate-limited to 1 request/second to respect the CTFTime ToS.

Flow:
1. Fetch recent writeup metadata from the CTFTime API (/api/v1/writeups/).
2. For each entry with a URL, fetch the external page with httpx.
3. Extract meaningful text (title + body) with minimal HTML parsing.
4. Chunk → embed → upsert into Qdrant.
5. Track ingested URLs in IngestionStateDB.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from typing import Any

import httpx
import structlog

from seraph.exceptions import WriteupIngestionError
from seraph.ingestion.chunker import chunk_markdown
from seraph.ingestion.models import IngestionRecord
from seraph.ingestion.state import IngestionStateDB

if False:  # TYPE_CHECKING
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

log = structlog.get_logger(__name__)

_CTFTIME_API = "https://ctftime.org/api/v1/writeups/"
_SOURCE_LABEL = "ctftime"
_RATE_LIMIT_SLEEP = 1.0  # seconds between requests
_TIMEOUT = httpx.Timeout(15.0)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s{3,}")


class CTFTimeScraper:
    """Scrapes and ingests writeups from CTFTime.

    Args:
        dense_embedder: Dense embedding model.
        sparse_embedder: BM25 sparse embedding model.
        vector_store: Qdrant vector store.
        state_db: Ingestion state tracker.
        rate_limit_sleep: Seconds to wait between HTTP requests.
    """

    def __init__(
        self,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        vector_store: QdrantStore,
        state_db: IngestionStateDB,
        rate_limit_sleep: float = _RATE_LIMIT_SLEEP,
    ) -> None:
        self._dense = dense_embedder
        self._sparse = sparse_embedder
        self._store = vector_store
        self._state = state_db
        self._rate_sleep = rate_limit_sleep
        self._last_request_time: float = 0.0

    async def ingest(
        self,
        limit: int = 50,
        force: bool = False,
    ) -> int:
        """Fetch and ingest recent CTFTime writeups.

        Args:
            limit: Maximum writeup entries to process.
            force: Re-ingest even if already tracked.

        Returns:
            Total chunk count ingested.

        Raises:
            WriteupIngestionError: On API or embedding failure.
        """
        log.info("ctftime_scraper.start", limit=limit)
        entries = await self._fetch_writeup_list(limit)

        ingested_chunks = 0
        for entry in entries:
            url = entry.get("url", "")
            if not url:
                continue
            try:
                chunks = await self._process_entry(entry, force=force)
                ingested_chunks += chunks
            except WriteupIngestionError as exc:
                log.warning("ctftime_scraper.entry_error", url=url, error=str(exc))

        log.info("ctftime_scraper.done", chunks=ingested_chunks)
        return ingested_chunks

    async def _fetch_writeup_list(self, limit: int) -> list[dict[str, Any]]:
        """Fetch writeup metadata from the CTFTime API.

        Returns a list of entry dicts on success, empty list on failure.
        """
        await self._rate_limit()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _CTFTIME_API,
                    params={"limit": limit},
                    headers={"User-Agent": "seraph-suite/0.1 (research; github.com/Unohana)"},
                )
                resp.raise_for_status()
                data = resp.json()
                # CTFTime returns {"results": [...]} or a plain list
                if isinstance(data, list):
                    return data[:limit]
                return data.get("results", [])[:limit]
        except Exception as exc:
            log.warning("ctftime_scraper.api_failed", error=str(exc))
            return []

    async def _process_entry(self, entry: dict[str, Any], force: bool) -> int:
        """Fetch, parse, and ingest a single CTFTime writeup entry.

        Returns the number of chunks ingested (0 if skipped).
        """
        url: str = entry.get("url", "")
        if not url:
            return 0

        if not force and await self._state.is_ingested(url, _SOURCE_LABEL):
            log.debug("ctftime_scraper.skip_existing", url=url)
            return 0

        await self._rate_limit()
        raw_html = await self._fetch_page(url)
        if not raw_html:
            return 0

        text = _strip_html(raw_html)
        if len(text) < 100:
            return 0

        title = entry.get("title", url)
        event = entry.get("event", {})
        event_title = event.get("title", "") if isinstance(event, dict) else ""
        content_hash = hashlib.sha256(text.encode()).hexdigest()

        metadata: dict[str, Any] = {
            "title": title,
            "source": _SOURCE_LABEL,
            "url": url,
            "event": event_title,
            "tags": entry.get("tags", []),
        }

        chunks = chunk_markdown(
            text=text,
            source=_SOURCE_LABEL,
            doc_id=content_hash,
            metadata=metadata,
        )
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        try:
            dense_vecs = await self._dense.embed_texts(texts)
            sparse_vecs = await self._sparse.embed_texts(texts)
        except Exception as exc:
            raise WriteupIngestionError(f"Embedding failed for {url}: {exc}") from exc

        try:
            await self._store.upsert_chunks(chunks, dense_vecs, sparse_vecs)
        except Exception as exc:
            raise WriteupIngestionError(f"Upsert failed for {url}: {exc}") from exc

        record = IngestionRecord(
            source_id=url,
            source=_SOURCE_LABEL,
            chunk_count=len(chunks),
        )
        await self._state.mark_ingested(record)
        log.info("ctftime_scraper.entry_done", url=url, chunks=len(chunks))
        return len(chunks)

    async def _fetch_page(self, url: str) -> str:
        """Fetch raw HTML from a URL.  Returns empty string on failure."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "seraph-suite/0.1 (research; github.com/Unohana)"},
                )
                resp.raise_for_status()
                return resp.text
        except Exception as exc:
            log.warning("ctftime_scraper.fetch_failed", url=url, error=str(exc))
            return ""

    async def _rate_limit(self) -> None:
        """Enforce minimum interval between HTTP requests."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_sleep:
            await asyncio.sleep(self._rate_sleep - elapsed)
        self._last_request_time = time.monotonic()


# ── HTML helpers ──────────────────────────────────────────────────────────────


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = _TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub("\n\n", text)
    return text.strip()
