"""Qdrant vector store client for the Seraph knowledge base.

Manages the ``seraph_kb`` collection with named dense (768d Cosine) and
sparse (BM25) vectors. Hybrid search uses Qdrant's built-in RRF fusion
via the ``query_points`` prefetch API.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import SparseVector

from seraph.agents.state import RetrievedDoc
from seraph.config import settings
from seraph.exceptions import VectorStoreError
from seraph.ingestion.models import DocumentChunk

log = structlog.get_logger(__name__)

# Deterministic UUID namespace for point IDs — never changes.
_UUID_NAMESPACE = uuid.UUID("7f3e9a2b-4c1d-4e8f-9b0a-1d2e3f4a5b6c")

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_DIM = 768


class QdrantStore:
    """Async Qdrant client wrapper for Seraph's knowledge base collection.

    All methods are async. Create one instance per application and reuse it.
    Call ``ensure_collection()`` on startup before upserting.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialise the store (does not connect yet).

        Args:
            url: Qdrant service URL. Defaults to ``settings.qdrant_url``.
            api_key: Optional API key. Defaults to ``settings.qdrant_api_key``.
            collection_name: Collection name. Defaults to ``settings.qdrant_collection_name``.
        """
        self._url = url or settings.qdrant_url
        self._api_key = api_key or settings.qdrant_api_key or None
        self._collection_name = collection_name or settings.qdrant_collection_name
        self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key)

    async def ensure_collection(self) -> None:
        """Create the collection if it does not already exist.

        The collection has two named vector spaces:
        - ``dense``: 768-dimensional Cosine similarity.
        - ``sparse``: BM25-style sparse vectors with IDF modifier.

        Raises:
            VectorStoreError: On Qdrant client error.
        """
        try:
            exists = await self._client.collection_exists(self._collection_name)
            if exists:
                log.debug("vectorstore.collection_exists", name=self._collection_name)
                return

            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=DENSE_DIM,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    )
                },
            )
            log.info("vectorstore.collection_created", name=self._collection_name)
        except Exception as exc:
            raise VectorStoreError(f"Failed to ensure collection: {exc}") from exc

    @staticmethod
    def _chunk_id_to_uuid(chunk_id: str) -> str:
        """Generate a deterministic UUID from a chunk ID string."""
        return str(uuid.uuid5(_UUID_NAMESPACE, chunk_id))

    async def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseVector],
    ) -> None:
        """Upsert document chunks with both dense and sparse vectors.

        Point IDs are derived deterministically from ``chunk.id`` so
        re-ingesting the same document is idempotent at the Qdrant level.

        Args:
            chunks: Document chunks with text and metadata.
            dense_vectors: Dense embedding for each chunk (same order).
            sparse_vectors: Sparse BM25 vector for each chunk (same order).

        Raises:
            VectorStoreError: On Qdrant upsert failure.
        """
        if not chunks:
            return
        if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
            raise VectorStoreError(
                "chunks, dense_vectors, and sparse_vectors must have the same length"
            )

        batch_size = settings.ingestion_batch_size
        try:
            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i : i + batch_size]
                batch_dense = dense_vectors[i : i + batch_size]
                batch_sparse = sparse_vectors[i : i + batch_size]

                points = [
                    models.PointStruct(
                        id=self._chunk_id_to_uuid(chunk.id),
                        vector={
                            DENSE_VECTOR_NAME: dense,
                            SPARSE_VECTOR_NAME: models.SparseVector(
                                indices=sparse.indices,
                                values=sparse.values,
                            ),
                        },
                        payload={
                            "text": chunk.text,
                            "source": chunk.source,
                            "doc_type": chunk.doc_type,
                            **chunk.metadata,
                        },
                    )
                    for chunk, dense, sparse in zip(
                        batch_chunks, batch_dense, batch_sparse, strict=True
                    )
                ]
                await self._client.upsert(collection_name=self._collection_name, points=points)
                log.debug("vectorstore.upsert_batch", count=len(points), offset=i)
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError(f"Upsert failed: {exc}") from exc

    async def hybrid_search(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        """Run hybrid BM25 + dense search with RRF fusion.

        Uses Qdrant's prefetch + FusionQuery(RRF) for server-side fusion.

        Args:
            dense_vector: Query dense embedding.
            sparse_vector: Query sparse BM25 vector.
            limit: Maximum results. Defaults to ``settings.max_retrieval_docs``.
            filters: Optional Qdrant filter dict (e.g. ``{"source": "nvd"}``).

        Returns:
            List of ``RetrievedDoc`` sorted by RRF-fused score (descending).

        Raises:
            VectorStoreError: On Qdrant query failure.
        """
        n = limit or settings.max_retrieval_docs
        qdrant_filter = _build_filter(filters) if filters else None
        prefetch_limit = n * 2  # Fetch more before fusion

        try:
            results = await self._client.query_points(
                collection_name=self._collection_name,
                prefetch=[
                    models.Prefetch(
                        query=dense_vector,
                        using=DENSE_VECTOR_NAME,
                        limit=prefetch_limit,
                        filter=qdrant_filter,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_vector.indices,
                            values=sparse_vector.values,
                        ),
                        using=SPARSE_VECTOR_NAME,
                        limit=prefetch_limit,
                        filter=qdrant_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=n,
                with_payload=True,
            )
        except Exception as exc:
            raise VectorStoreError(f"Hybrid search failed: {exc}") from exc

        return [
            RetrievedDoc(
                id=str(point.id),
                score=point.score,
                text=point.payload.get("text", "") if point.payload else "",
                source=point.payload.get("source", "") if point.payload else "",
                metadata={
                    k: v for k, v in (point.payload or {}).items() if k not in ("text", "source")
                },
            )
            for point in results.points
        ]

    async def delete_by_source(self, source: str) -> None:
        """Delete all points matching a given source name.

        Args:
            source: Source identifier (e.g. ``"nvd"``, ``"exploitdb"``).

        Raises:
            VectorStoreError: On Qdrant delete failure.
        """
        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="source", match=models.MatchValue(value=source)
                            )
                        ]
                    )
                ),
            )
            log.info("vectorstore.deleted_by_source", source=source)
        except Exception as exc:
            raise VectorStoreError(f"Delete by source failed: {exc}") from exc

    async def count(self) -> int:
        """Return total number of points in the collection.

        Raises:
            VectorStoreError: On Qdrant failure.
        """
        try:
            result = await self._client.count(collection_name=self._collection_name, exact=True)
            return result.count
        except Exception as exc:
            raise VectorStoreError(f"Count failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying Qdrant client connection."""
        await self._client.close()
        log.debug("vectorstore.closed")


def _build_filter(filters: dict[str, Any]) -> models.Filter:
    """Build a Qdrant ``Filter`` from a simple key=value dict.

    Args:
        filters: Dict of payload field names to match values.

    Returns:
        Qdrant ``Filter`` with ``must`` conditions.
    """
    conditions = [
        models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in filters.items()
    ]
    return models.Filter(must=conditions)
