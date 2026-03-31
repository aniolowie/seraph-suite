"""Unit tests for CrossEncoderReranker."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from seraph.agents.state import RetrievedDoc
from seraph.exceptions import RerankerError
from seraph.knowledge.reranker import CrossEncoderReranker


def _make_doc(doc_id: str, score: float = 0.5, text: str = "sample") -> RetrievedDoc:
    return RetrievedDoc(id=doc_id, score=score, text=text, source="nvd")


class TestCrossEncoderReranker:
    def test_lazy_loading(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        assert reranker._model is None

    async def test_empty_documents_returns_empty(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []

    async def test_reranking_sorts_by_score_descending(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        docs = [_make_doc("a"), _make_doc("b"), _make_doc("c")]

        mock_model = MagicMock()
        # Return scores: a=0.1, b=0.9, c=0.5
        mock_model.predict = MagicMock(return_value=np.array([0.1, 0.9, 0.5]))
        reranker._model = mock_model

        result = await reranker.rerank("query", docs)
        assert result[0].id == "b"
        assert result[1].id == "c"
        assert result[2].id == "a"

    async def test_top_k_truncation(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        docs = [_make_doc(f"doc-{i}") for i in range(10)]

        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=np.arange(10, dtype=np.float32))
        reranker._model = mock_model

        result = await reranker.rerank("query", docs, top_k=3)
        assert len(result) == 3

    async def test_scores_are_updated(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        docs = [_make_doc("a", score=0.0), _make_doc("b", score=0.0)]

        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=np.array([0.7, 0.3]))
        reranker._model = mock_model

        result = await reranker.rerank("query", docs)
        assert result[0].score == pytest.approx(0.7, abs=1e-4)
        assert result[1].score == pytest.approx(0.3, abs=1e-4)

    async def test_model_failure_raises_reranker_error(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        docs = [_make_doc("a")]

        mock_model = MagicMock()
        mock_model.predict = MagicMock(side_effect=RuntimeError("model crash"))
        reranker._model = mock_model

        with pytest.raises(RerankerError):
            await reranker.rerank("query", docs)

    async def test_top_k_none_returns_all(self) -> None:
        reranker = CrossEncoderReranker(model_name="test-model")
        docs = [_make_doc(f"doc-{i}") for i in range(5)]

        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=np.ones(5, dtype=np.float32))
        reranker._model = mock_model

        result = await reranker.rerank("query", docs, top_k=None)
        assert len(result) == 5
