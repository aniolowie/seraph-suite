"""HybridRetriever — the single entry point for all KB retrieval.

Pipeline: parallel embed (dense + sparse) → Qdrant RRF hybrid search
→ cross-encoder rerank → return top-K RetrievedDoc objects.

Agents call ``retriever.retrieve(query)`` and never touch the
underlying components directly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from seraph.agents.state import RetrievedDoc
from seraph.config import settings
from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
from seraph.knowledge.reranker import CrossEncoderReranker
from seraph.knowledge.vectorstore import QdrantStore

log = structlog.get_logger(__name__)


class HybridRetriever:
    """Orchestrates the full retrieval pipeline for Seraph agents.

    Composes :class:`DenseEmbedder`, :class:`SparseEmbedder`,
    :class:`QdrantStore`, and :class:`CrossEncoderReranker` into a
    single ``retrieve(query)`` interface.

    All components are injected via the constructor so they can be
    mocked in tests.
    """

    def __init__(
        self,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        vector_store: QdrantStore,
        reranker: CrossEncoderReranker,
    ) -> None:
        """Initialise with all four pipeline components.

        Args:
            dense_embedder: Dense embedding wrapper (nomic-embed).
            sparse_embedder: Sparse BM25 embedding wrapper.
            vector_store: Qdrant hybrid search client.
            reranker: Cross-encoder reranker.
        """
        self._dense = dense_embedder
        self._sparse = sparse_embedder
        self._store = vector_store
        self._reranker = reranker

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        """Retrieve and rerank documents for ``query``.

        Steps:
        1. Embed query with dense and sparse embedders in parallel.
        2. Run Qdrant hybrid search (RRF fusion of BM25 + dense).
        3. Cross-encoder rerank the top candidates.

        Args:
            query: Free-text search query.
            top_k: Number of results after reranking. Defaults to ``settings.rerank_top_k``.
            filters: Optional payload filters passed to Qdrant (e.g. ``{"source": "nvd"}``).

        Returns:
            Reranked list of ``RetrievedDoc``, highest relevance first.
        """
        k = top_k if top_k is not None else settings.rerank_top_k
        log.debug("retriever.retrieve", query=query[:80], top_k=k, filters=filters)

        # Step 1: Embed in parallel.
        dense_vec, sparse_vec = await asyncio.gather(
            self._dense.embed_query(query),
            self._sparse.embed_query(query),
        )

        # Step 2: Hybrid search — fetch more than needed for reranking.
        candidates = await self._store.hybrid_search(
            dense_vector=dense_vec,
            sparse_vector=sparse_vec,
            limit=settings.max_retrieval_docs,
            filters=filters,
        )

        if not candidates:
            log.debug("retriever.no_candidates", query=query[:80])
            return []

        # Step 3: Rerank and truncate to top_k.
        reranked = await self._reranker.rerank(query, candidates, top_k=k)
        log.debug("retriever.done", candidates=len(candidates), returned=len(reranked))
        return reranked

    async def retrieve_without_rerank(
        self,
        query: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        """Retrieve documents without cross-encoder reranking.

        Cheaper than :meth:`retrieve`. Use for bulk operations where
        reranking overhead is not justified.

        Args:
            query: Free-text search query.
            limit: Maximum results. Defaults to ``settings.max_retrieval_docs``.
            filters: Optional payload filters.

        Returns:
            RRF-fused results without reranking, sorted by Qdrant score.
        """
        n = limit if limit is not None else settings.max_retrieval_docs
        log.debug("retriever.retrieve_no_rerank", query=query[:80], limit=n)

        dense_vec, sparse_vec = await asyncio.gather(
            self._dense.embed_query(query),
            self._sparse.embed_query(query),
        )

        return await self._store.hybrid_search(
            dense_vector=dense_vec,
            sparse_vector=sparse_vec,
            limit=n,
            filters=filters,
        )
