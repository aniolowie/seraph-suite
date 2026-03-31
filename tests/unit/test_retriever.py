"""Unit tests for HybridRetriever."""

from __future__ import annotations

from unittest.mock import AsyncMock

from qdrant_client.models import SparseVector

from seraph.agents.state import RetrievedDoc
from seraph.knowledge.retriever import HybridRetriever


def _make_doc(doc_id: str, score: float = 0.8) -> RetrievedDoc:
    return RetrievedDoc(id=doc_id, score=score, text="sample doc", source="nvd")


def _make_sparse() -> SparseVector:
    return SparseVector(indices=[1], values=[0.9])


class TestHybridRetriever:
    def _make_retriever(
        self,
        candidate_docs: list[RetrievedDoc] | None = None,
        reranked_docs: list[RetrievedDoc] | None = None,
    ) -> HybridRetriever:
        docs = (
            candidate_docs
            if candidate_docs is not None
            else [_make_doc("doc-1"), _make_doc("doc-2")]
        )
        final = reranked_docs if reranked_docs is not None else docs

        dense_embedder = AsyncMock()
        dense_embedder.embed_query = AsyncMock(return_value=[0.1] * 768)

        sparse_embedder = AsyncMock()
        sparse_embedder.embed_query = AsyncMock(return_value=_make_sparse())

        vector_store = AsyncMock()
        vector_store.hybrid_search = AsyncMock(return_value=docs)

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=final)

        return HybridRetriever(
            dense_embedder=dense_embedder,
            sparse_embedder=sparse_embedder,
            vector_store=vector_store,
            reranker=reranker,
        )

    async def test_retrieve_returns_reranked_docs(self) -> None:
        retriever = self._make_retriever()
        results = await retriever.retrieve("log4j JNDI injection")
        assert len(results) == 2

    async def test_both_embedders_are_called(self) -> None:
        retriever = self._make_retriever()
        await retriever.retrieve("test query")
        retriever._dense.embed_query.assert_awaited_once_with("test query")
        retriever._sparse.embed_query.assert_awaited_once_with("test query")

    async def test_filters_passed_to_vector_store(self) -> None:
        retriever = self._make_retriever()
        await retriever.retrieve("query", filters={"source": "nvd"})
        call_kwargs = retriever._store.hybrid_search.call_args.kwargs
        assert call_kwargs["filters"] == {"source": "nvd"}

    async def test_reranker_called_with_candidates(self) -> None:
        candidate_docs = [_make_doc("a"), _make_doc("b"), _make_doc("c")]
        retriever = self._make_retriever(candidate_docs=candidate_docs)
        await retriever.retrieve("query", top_k=2)
        retriever._reranker.rerank.assert_awaited_once()
        _, call_kwargs = retriever._reranker.rerank.call_args
        assert call_kwargs.get("top_k") == 2 or retriever._reranker.rerank.call_args.args[2] == 2

    async def test_empty_candidates_returns_empty(self) -> None:
        retriever = self._make_retriever(candidate_docs=[])
        retriever._reranker.rerank = AsyncMock(return_value=[])
        results = await retriever.retrieve("query")
        assert results == []
        retriever._reranker.rerank.assert_not_awaited()

    async def test_retrieve_without_rerank_skips_reranker(self) -> None:
        retriever = self._make_retriever()
        results = await retriever.retrieve_without_rerank("query")
        retriever._reranker.rerank.assert_not_awaited()
        assert len(results) == 2

    async def test_retrieve_without_rerank_passes_limit(self) -> None:
        retriever = self._make_retriever()
        await retriever.retrieve_without_rerank("query", limit=5)
        call_kwargs = retriever._store.hybrid_search.call_args.kwargs
        assert call_kwargs["limit"] == 5
