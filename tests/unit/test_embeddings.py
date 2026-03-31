"""Unit tests for DenseEmbedder and SparseEmbedder."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from qdrant_client.models import SparseVector

from seraph.exceptions import EmbeddingError
from seraph.knowledge.embeddings import _DOC_PREFIX, _QUERY_PREFIX, DenseEmbedder, SparseEmbedder


class TestDenseEmbedder:
    def test_lazy_loading(self) -> None:
        embedder = DenseEmbedder(model_name="test-model")
        assert embedder._model is None  # not loaded yet

    async def test_embed_texts_prepends_doc_prefix(self) -> None:
        embedder = DenseEmbedder(model_name="test-model")
        captured: list[list[str]] = []

        def fake_encode(texts: list[str], **kwargs: object) -> np.ndarray:
            captured.extend([texts])
            return np.ones((len(texts), 768), dtype=np.float32)

        mock_model = MagicMock()
        mock_model.encode = fake_encode
        embedder._model = mock_model

        await embedder.embed_texts(["Apache Log4j2"])
        assert captured[0][0].startswith(_DOC_PREFIX)

    async def test_embed_query_prepends_query_prefix(self) -> None:
        embedder = DenseEmbedder(model_name="test-model")
        captured: list[list[str]] = []

        def fake_encode(texts: list[str], **kwargs: object) -> np.ndarray:
            captured.extend([texts])
            return np.ones((len(texts), 768), dtype=np.float32)

        mock_model = MagicMock()
        mock_model.encode = fake_encode
        embedder._model = mock_model

        await embedder.embed_query("find log4j exploits")
        assert any(_QUERY_PREFIX in t for texts in captured for t in texts)

    async def test_embed_texts_returns_correct_dimension(self) -> None:
        embedder = DenseEmbedder(model_name="test-model")
        mock_model = MagicMock()
        mock_model.encode = lambda texts, **kw: np.ones((len(texts), 768), dtype=np.float32)
        embedder._model = mock_model

        results = await embedder.embed_texts(["text1", "text2"])
        assert len(results) == 2
        assert all(len(v) == 768 for v in results)

    async def test_embed_texts_empty_returns_empty(self) -> None:
        embedder = DenseEmbedder()
        assert await embedder.embed_texts([]) == []

    async def test_embed_texts_raises_embedding_error_on_failure(self) -> None:
        embedder = DenseEmbedder(model_name="test-model")
        mock_model = MagicMock()
        mock_model.encode = MagicMock(side_effect=RuntimeError("model error"))
        embedder._model = mock_model

        with pytest.raises(EmbeddingError):
            await embedder.embed_texts(["text"])

    def test_dimension_property(self) -> None:
        assert DenseEmbedder().dimension == 768


class TestSparseEmbedder:
    def test_lazy_loading(self) -> None:
        embedder = SparseEmbedder(model_name="Qdrant/bm25")
        assert embedder._model is None

    async def test_embed_texts_returns_sparse_vectors(self) -> None:
        embedder = SparseEmbedder(model_name="Qdrant/bm25")

        class FakeSparseEmbedding:
            indices = np.array([1, 5, 10], dtype=np.int32)
            values = np.array([0.3, 0.5, 0.2], dtype=np.float32)

        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=[FakeSparseEmbedding(), FakeSparseEmbedding()])
        embedder._model = mock_model

        results = await embedder.embed_texts(["text1", "text2"])
        assert len(results) == 2
        assert all(isinstance(r, SparseVector) for r in results)
        assert results[0].indices == [1, 5, 10]
        assert results[0].values == pytest.approx([0.3, 0.5, 0.2], abs=1e-4)

    async def test_embed_texts_empty_returns_empty(self) -> None:
        embedder = SparseEmbedder()
        assert await embedder.embed_texts([]) == []

    async def test_embed_query_returns_sparse_vector(self) -> None:
        embedder = SparseEmbedder(model_name="Qdrant/bm25")

        class FakeSE:
            indices = np.array([2], dtype=np.int32)
            values = np.array([1.0], dtype=np.float32)

        mock_model = MagicMock()
        mock_model.embed = MagicMock(return_value=[FakeSE()])
        embedder._model = mock_model

        result = await embedder.embed_query("apache")
        assert isinstance(result, SparseVector)

    async def test_embed_raises_embedding_error_on_failure(self) -> None:
        embedder = SparseEmbedder(model_name="Qdrant/bm25")
        mock_model = MagicMock()
        mock_model.embed = MagicMock(side_effect=RuntimeError("sparse model error"))
        embedder._model = mock_model

        with pytest.raises(EmbeddingError):
            await embedder.embed_texts(["text"])
