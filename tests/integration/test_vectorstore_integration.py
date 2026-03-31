"""Integration tests for QdrantStore against a real Qdrant container.

Requires: docker compose up -d (Qdrant on localhost:6333)
"""

from __future__ import annotations

import pytest
from qdrant_client.models import SparseVector

from seraph.ingestion.models import DocumentChunk

pytestmark = pytest.mark.integration


def _make_chunk(chunk_id: str, source: str = "nvd") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        text=f"[CVE-TEST] Description for {chunk_id}",
        source=source,
        doc_type="cve",
        metadata={"cve_id": chunk_id, "cvss_score": 7.5},
    )


def _fake_dense(n: int = 1) -> list[list[float]]:
    return [[0.1] * 768] * n


def _fake_sparse(n: int = 1) -> list[SparseVector]:
    return [SparseVector(indices=[1, 5, 100], values=[0.3, 0.5, 0.2])] * n


class TestQdrantStoreIntegration:
    async def test_collection_created(self, qdrant_store: object) -> None:
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        count = await store.count()
        assert count == 0

    async def test_upsert_and_count(self, qdrant_store: object) -> None:
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        chunks = [_make_chunk(f"CVE-TEST-{i:03d}") for i in range(5)]
        await store.upsert_chunks(chunks, _fake_dense(5), _fake_sparse(5))
        assert await store.count() == 5

    async def test_upsert_is_idempotent(self, qdrant_store: object) -> None:
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        chunks = [_make_chunk("CVE-TEST-001")]
        await store.upsert_chunks(chunks, _fake_dense(1), _fake_sparse(1))
        await store.upsert_chunks(chunks, _fake_dense(1), _fake_sparse(1))
        assert await store.count() == 1  # same UUID, not duplicated

    async def test_hybrid_search_returns_results(self, qdrant_store: object) -> None:
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        chunks = [_make_chunk(f"CVE-TEST-{i:03d}") for i in range(3)]
        await store.upsert_chunks(chunks, _fake_dense(3), _fake_sparse(3))

        results = await store.hybrid_search(
            dense_vector=[0.1] * 768,
            sparse_vector=SparseVector(indices=[1], values=[1.0]),
            limit=3,
        )
        assert len(results) > 0
        assert all(r.source == "nvd" for r in results)

    async def test_delete_by_source(self, qdrant_store: object) -> None:
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        chunks_nvd = [_make_chunk("CVE-NVD-001", source="nvd")]
        chunks_edb = [_make_chunk("EDB-001", source="exploitdb")]
        await store.upsert_chunks(chunks_nvd, _fake_dense(1), _fake_sparse(1))
        await store.upsert_chunks(chunks_edb, _fake_dense(1), _fake_sparse(1))

        await store.delete_by_source("nvd")

        # Only exploitdb doc should remain.
        assert await store.count() == 1
