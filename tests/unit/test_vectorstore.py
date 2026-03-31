"""Unit tests for QdrantStore (mocked AsyncQdrantClient)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import SparseVector

from seraph.exceptions import VectorStoreError
from seraph.ingestion.models import DocumentChunk
from seraph.knowledge.vectorstore import QdrantStore


def _make_chunk(chunk_id: str, source: str = "nvd") -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        text=f"[CVE-TEST] Test text for {chunk_id}",
        source=source,
        doc_type="cve",
        metadata={"cve_id": chunk_id, "cvss_score": 7.5},
    )


def _make_sparse() -> SparseVector:
    return SparseVector(indices=[1, 5, 10], values=[0.3, 0.5, 0.2])


class TestQdrantStoreChunkIdToUuid:
    def test_deterministic(self) -> None:
        uid1 = QdrantStore._chunk_id_to_uuid("CVE-2021-44228-0")
        uid2 = QdrantStore._chunk_id_to_uuid("CVE-2021-44228-0")
        assert uid1 == uid2

    def test_different_ids_produce_different_uuids(self) -> None:
        uid1 = QdrantStore._chunk_id_to_uuid("CVE-2021-44228-0")
        uid2 = QdrantStore._chunk_id_to_uuid("CVE-2021-44229-0")
        assert uid1 != uid2

    def test_valid_uuid_format(self) -> None:
        uid = QdrantStore._chunk_id_to_uuid("CVE-2021-44228-0")
        parsed = uuid.UUID(uid)  # raises if invalid
        assert str(parsed) == uid


class TestQdrantStoreEnsureCollection:
    async def test_creates_collection_when_not_exists(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=False)
        mock_client.create_collection = AsyncMock()
        store._client = mock_client

        await store.ensure_collection()
        mock_client.create_collection.assert_awaited_once()

    async def test_skips_creation_when_already_exists(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(return_value=True)
        mock_client.create_collection = AsyncMock()
        store._client = mock_client

        await store.ensure_collection()
        mock_client.create_collection.assert_not_awaited()

    async def test_raises_vector_store_error_on_failure(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        mock_client.collection_exists = AsyncMock(side_effect=RuntimeError("connection refused"))
        store._client = mock_client

        with pytest.raises(VectorStoreError):
            await store.ensure_collection()


class TestQdrantStoreUpsert:
    async def test_upsert_calls_client(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock()
        store._client = mock_client

        chunks = [_make_chunk("CVE-001")]
        dense = [[0.1] * 768]
        sparse = [_make_sparse()]

        await store.upsert_chunks(chunks, dense, sparse)
        mock_client.upsert.assert_awaited_once()

    async def test_empty_chunks_no_upsert(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        store._client = mock_client

        await store.upsert_chunks([], [], [])
        mock_client.upsert.assert_not_awaited()

    async def test_length_mismatch_raises_error(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        store._client = AsyncMock()

        with pytest.raises(VectorStoreError, match="same length"):
            await store.upsert_chunks(
                [_make_chunk("CVE-001")],
                [],  # wrong length
                [_make_sparse()],
            )

    async def test_batching_respects_batch_size(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        mock_client.upsert = AsyncMock()
        store._client = mock_client

        # Create 5 chunks with batch_size=2 → should call upsert 3 times.

        chunks = [_make_chunk(f"CVE-{i:03d}") for i in range(5)]
        dense = [[0.1] * 768] * 5
        sparse = [_make_sparse()] * 5

        with patch("seraph.knowledge.vectorstore.settings") as mock_settings:
            mock_settings.ingestion_batch_size = 2
            await store.upsert_chunks(chunks, dense, sparse)

        assert mock_client.upsert.await_count == 3  # ceil(5/2) = 3


class TestQdrantStoreCount:
    async def test_count_returns_integer(self) -> None:
        store = QdrantStore(url="http://localhost:6333", collection_name="test")
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.count = 42
        mock_client.count = AsyncMock(return_value=mock_result)
        store._client = mock_client

        result = await store.count()
        assert result == 42
