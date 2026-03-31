"""Cross-encoder reranker for the Seraph retrieval pipeline.

Uses BAAI/bge-reranker-v2-m3 (local) to re-score top-K documents
retrieved by the initial hybrid search. The reranker sees both the
query and the document text, producing a more accurate relevance score.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from seraph.agents.state import RetrievedDoc
from seraph.config import settings
from seraph.exceptions import RerankerError

log = structlog.get_logger(__name__)


class CrossEncoderReranker:
    """Wraps bge-reranker-v2-m3 for cross-encoder reranking.

    Lazy-loads the model on first call. All inference is run in a thread
    pool via ``asyncio.to_thread()`` to keep the event loop unblocked.
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Initialise without loading the model.

        Args:
            model_name: HuggingFace model ID. Defaults to settings value.
        """
        self._model_name = model_name or settings.reranker_model
        self._model: Any = None  # sentence_transformers.CrossEncoder

    def _load_model(self) -> Any:
        """Load the CrossEncoder model (cached after first load)."""
        if self._model is None:
            import time

            from sentence_transformers import CrossEncoder

            t0 = time.monotonic()
            self._model = CrossEncoder(
                self._model_name,
                max_length=512,
                cache_folder=str(settings.models_dir),
            )
            log.info(
                "reranker.loaded",
                model=self._model_name,
                elapsed_s=round(time.monotonic() - t0, 2),
            )
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[RetrievedDoc],
        top_k: int | None = None,
    ) -> list[RetrievedDoc]:
        """Re-score documents with the cross-encoder and return top-K.

        Each ``RetrievedDoc.score`` is updated with the cross-encoder score.
        Documents are returned in descending score order.

        Args:
            query: The search query.
            documents: Candidate documents from initial retrieval.
            top_k: Maximum number of documents to return. Defaults to all.

        Returns:
            Reranked documents (highest score first), truncated to ``top_k``.

        Raises:
            RerankerError: On model or inference failure.
        """
        if not documents:
            return []

        k = top_k if top_k is not None else len(documents)

        try:
            model = self._load_model()
            pairs = [(query, doc.text) for doc in documents]
            scores: list[float] = await asyncio.to_thread(
                lambda: model.predict(pairs, show_progress_bar=False).tolist()
            )
        except Exception as exc:
            raise RerankerError(f"Cross-encoder reranking failed: {exc}") from exc

        # Update scores and sort descending.
        reranked = [
            doc.model_copy(update={"score": float(score)})
            for doc, score in zip(documents, scores, strict=True)
        ]
        reranked.sort(key=lambda d: d.score, reverse=True)
        return reranked[:k]
