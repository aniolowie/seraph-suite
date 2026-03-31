"""NVD CVE JSON feed ingestion pipeline.

Fetches from NVD API v2, parses CVE descriptions and metadata,
and upserts into the Qdrant knowledge base with SQLite idempotency.

Rate limits: 5 req/30s without API key, 50 req/30s with API key.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from seraph.config import settings
from seraph.exceptions import NVDIngestionError
from seraph.ingestion.chunker import prepend_source_tag, single_chunk
from seraph.ingestion.models import DocumentChunk, IngestionRecord
from seraph.ingestion.state import IngestionStateDB
from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
from seraph.knowledge.vectorstore import QdrantStore

log = structlog.get_logger(__name__)

_RESULTS_PER_PAGE = 2000
# Delay between requests: 7s without key (conservative), 1s with key.
_RATE_DELAY_NO_KEY = 7.0
_RATE_DELAY_WITH_KEY = 1.0


class NVDIngestor:
    """Fetches, parses, and ingests NVD CVE data into the Seraph KB.

    Typical usage::

        ingestor = NVDIngestor(dense_embedder, sparse_embedder, store, state_db)
        await ingestor.ingest(year=2024)
    """

    def __init__(
        self,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        vector_store: QdrantStore,
        state_db: IngestionStateDB,
    ) -> None:
        """Initialise the ingestor with required pipeline components.

        Args:
            dense_embedder: Dense embedding wrapper.
            sparse_embedder: Sparse BM25 embedding wrapper.
            vector_store: Qdrant store for upserts.
            state_db: SQLite idempotency tracker.
        """
        self._dense = dense_embedder
        self._sparse = sparse_embedder
        self._store = vector_store
        self._state_db = state_db
        self._rate_delay = _RATE_DELAY_NO_KEY if not settings.nvd_api_key else _RATE_DELAY_WITH_KEY

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if settings.nvd_api_key:
            headers["apiKey"] = settings.nvd_api_key
        return headers

    async def fetch_cves(
        self,
        year: int | None = None,
        keyword: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async generator that yields raw CVE dicts from NVD API v2.

        Handles pagination automatically. Applies exponential backoff on
        429/503 responses.

        Args:
            year: Filter to CVEs published in this year.
            keyword: Keyword filter for NVD API.

        Yields:
            Raw CVE JSON objects from the NVD ``vulnerabilities`` array.

        Raises:
            NVDIngestionError: On persistent HTTP failures.
        """
        params: dict[str, Any] = {"resultsPerPage": _RESULTS_PER_PAGE, "startIndex": 0}
        if year is not None:
            params["pubStartDate"] = f"{year}-01-01T00:00:00.000"
            params["pubEndDate"] = f"{year}-12-31T23:59:59.999"
        if keyword:
            params["keywordSearch"] = keyword

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await self._fetch_with_retry(client, params)
                data = response.json()
                vulns: list[dict[str, Any]] = data.get("vulnerabilities", [])
                for v in vulns:
                    yield v

                total: int = data.get("totalResults", 0)
                fetched_so_far: int = params["startIndex"] + len(vulns)
                log.debug("nvd.page_fetched", fetched=fetched_so_far, total=total)

                if fetched_so_far >= total:
                    break

                params = {**params, "startIndex": fetched_so_far}
                await asyncio.sleep(self._rate_delay)

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        params: dict[str, Any],
        max_retries: int = 5,
    ) -> httpx.Response:
        """Fetch one page with exponential backoff on rate-limit errors."""
        delay = self._rate_delay
        for attempt in range(max_retries):
            try:
                response = await client.get(
                    settings.nvd_api_base_url,
                    params=params,
                    headers=self._build_headers(),
                )
                if response.status_code in (429, 503):
                    wait = delay * (2**attempt)
                    log.warning("nvd.rate_limited", status=response.status_code, wait_s=wait)
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if attempt == max_retries - 1:
                    raise NVDIngestionError(f"NVD API request failed: {exc}") from exc
                await asyncio.sleep(delay * (2**attempt))
        raise NVDIngestionError("NVD API max retries exceeded")  # unreachable but mypy happy

    def parse_cve(self, raw: dict[str, Any]) -> DocumentChunk | None:
        """Parse a raw NVD CVE JSON object into a ``DocumentChunk``.

        Args:
            raw: One entry from the NVD ``vulnerabilities`` array.

        Returns:
            ``DocumentChunk`` ready for embedding, or ``None`` if the CVE
            has no usable English description.
        """
        cve = raw.get("cve", {})
        cve_id: str = cve.get("id", "")
        if not cve_id:
            return None

        description = _extract_english_description(cve)
        if not description:
            log.debug("nvd.skip_no_description", cve_id=cve_id)
            return None

        cvss_score, severity = _extract_cvss(cve)
        published = cve.get("published", "")
        cwe_ids = _extract_cwe_ids(cve)

        text = prepend_source_tag(single_chunk(description), cve_id)

        return DocumentChunk(
            id=f"{cve_id}-0",
            text=text,
            source="nvd",
            doc_type="cve",
            metadata={
                "cve_id": cve_id,
                "cvss_score": cvss_score,
                "severity": severity,
                "published_date": published[:10] if published else "",
                "cwe_ids": cwe_ids,
                "chunk_index": 0,
                "total_chunks": 1,
            },
        )

    async def ingest(self, year: int | None = None, keyword: str | None = None) -> int:
        """Run the full NVD ingestion pipeline.

        Fetches CVEs, skips already-ingested ones, embeds and upserts the
        rest in batches, then records results in the state DB.

        Args:
            year: Ingest only CVEs published in this year. ``None`` = all.
            keyword: Optional NVD keyword filter.

        Returns:
            Number of newly ingested CVEs.

        Raises:
            NVDIngestionError: On persistent pipeline failure.
        """
        await self._state_db.init_db()
        await self._store.ensure_collection()

        batch: list[DocumentChunk] = []
        total_ingested = 0

        async def _flush(b: list[DocumentChunk]) -> int:
            if not b:
                return 0
            dense_vecs, sparse_vecs = await asyncio.gather(
                self._dense.embed_texts([c.text for c in b]),
                self._sparse.embed_texts([c.text for c in b]),
            )
            await self._store.upsert_chunks(b, dense_vecs, sparse_vecs)
            for chunk in b:
                await self._state_db.mark_ingested(
                    IngestionRecord(source_id=chunk.metadata["cve_id"], source="nvd", chunk_count=1)
                )
            log.info("nvd.batch_ingested", count=len(b))
            return len(b)

        try:
            async for raw in self.fetch_cves(year=year, keyword=keyword):
                cve_id = raw.get("cve", {}).get("id", "")
                if not cve_id or await self._state_db.is_ingested(cve_id, "nvd"):
                    continue

                chunk = self.parse_cve(raw)
                if chunk is None:
                    continue

                batch.append(chunk)
                if len(batch) >= settings.ingestion_batch_size:
                    total_ingested += await _flush(batch)
                    batch = []

            total_ingested += await _flush(batch)
        except NVDIngestionError:
            raise
        except Exception as exc:
            raise NVDIngestionError(f"NVD ingestion pipeline failed: {exc}") from exc

        log.info("nvd.ingestion_complete", total=total_ingested, year=year)
        return total_ingested


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_english_description(cve: dict[str, Any]) -> str:
    """Extract the first English description from a CVE object."""
    for desc in cve.get("descriptions", []):
        if desc.get("lang", "") == "en":
            return desc.get("value", "").strip()
    return ""


def _extract_cvss(cve: dict[str, Any]) -> tuple[float, str]:
    """Extract CVSS v3.1 base score and severity. Falls back to v3.0, then v2."""
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key, [])
        if entries:
            data = entries[0].get("cvssData", {})
            score = float(data.get("baseScore", 0.0))
            severity = data.get("baseSeverity", data.get("vectorString", "UNKNOWN"))
            return score, str(severity)
    return 0.0, "UNKNOWN"


def _extract_cwe_ids(cve: dict[str, Any]) -> list[str]:
    """Extract CWE IDs from CVE weaknesses list."""
    ids: list[str] = []
    for weakness in cve.get("weaknesses", []):
        for desc in weakness.get("description", []):
            val = desc.get("value", "")
            if val.startswith("CWE-"):
                ids.append(val)
    return ids
