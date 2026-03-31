"""Dense and sparse embedding wrappers for the Seraph knowledge base.

Dense: nomic-embed-text-v1.5 via sentence-transformers (768d, Matryoshka).
Sparse: BM25 via fastembed (Qdrant/bm25).

Both use lazy loading — models are downloaded/loaded on first call only.
All I/O is async via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from qdrant_client.models import SparseVector

from seraph.config import settings
from seraph.exceptions import EmbeddingError

if TYPE_CHECKING:
    from seraph.learning.projection import QueryProjection

log = structlog.get_logger(__name__)

# nomic-embed requires task-specific prefixes for best quality.
_QUERY_PREFIX = "search_query: "
_DOC_PREFIX = "search_document: "


class DenseEmbedder:
    """Wraps nomic-embed-text-v1.5 for dense 768-dimensional embeddings.

    Uses task prefixes as required by the nomic-embed specification:
    - Documents: ``search_document: <text>``
    - Queries: ``search_query: <text>``
    """

    def __init__(
        self,
        model_name: str | None = None,
        projection: QueryProjection | None = None,
    ) -> None:
        """Initialise without loading the model (lazy load on first call).

        Args:
            model_name: HuggingFace model ID. Defaults to settings value.
            projection: Optional ``QueryProjection`` applied to query vectors.
        """
        self._model_name = model_name or settings.dense_embedding_model
        self._model: Any = None  # sentence_transformers.SentenceTransformer
        self._lora_adapter_path: Path | None = None
        self._projection: QueryProjection | None = projection

    def _load_model(self) -> Any:
        """Load the sentence-transformers model (cached after first load)."""
        if self._model is None:
            import time

            from sentence_transformers import SentenceTransformer

            t0 = time.monotonic()
            self._model = SentenceTransformer(
                self._model_name,
                cache_folder=str(settings.models_dir),
                trust_remote_code=True,
            )
            elapsed = round(time.monotonic() - t0, 2)
            log.info("dense_embedder.loaded", model=self._model_name, elapsed_s=elapsed)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts.

        Prepends ``search_document:`` prefix to each text.

        Args:
            texts: Document texts to embed.

        Returns:
            List of 768-dimensional float vectors.

        Raises:
            EmbeddingError: On model or encoding failure.
        """
        if not texts:
            return []
        try:
            prefixed = [f"{_DOC_PREFIX}{t}" for t in texts]
            model = self._load_model()
            vecs: Any = await asyncio.to_thread(model.encode, prefixed, normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        except Exception as exc:
            raise EmbeddingError(f"Dense embedding failed: {exc}") from exc

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string, optionally applying the LoRA projection.

        Prepends ``search_query:`` prefix, then passes the vector through
        ``self._projection`` if one is configured.

        Args:
            query: Query text.

        Returns:
            768-dimensional float vector.

        Raises:
            EmbeddingError: On model or encoding failure.
        """
        try:
            model = self._load_model()
            prefixed = f"{_QUERY_PREFIX}{query}"
            vec: Any = await asyncio.to_thread(model.encode, [prefixed], normalize_embeddings=True)
            base_vec: list[float] = vec[0].tolist()
        except Exception as exc:
            raise EmbeddingError(f"Dense query embedding failed: {exc}") from exc

        if self._projection is not None:
            from seraph.exceptions import ProjectionError

            try:
                base_vec = await self._projection.project(base_vec)
            except ProjectionError as exc:
                log.warning("dense_embedder.projection_failed", error=str(exc))

        return base_vec

    def load_lora_adapter(self, adapter_path: Path) -> None:
        """Hot-load a LoRA adapter into the sentence-transformers model.

        Resets the cached model so the adapter is picked up on the next
        ``embed_texts`` / ``embed_query`` call.

        Args:
            adapter_path: Directory containing the PEFT adapter files.

        Raises:
            EmbeddingError: If the adapter cannot be loaded.
        """
        try:
            from peft import PeftModel

            base = self._load_model()
            # sentence-transformers wraps a HuggingFace model inside `[0].auto_model`
            hf_model = base[0].auto_model  # type: ignore[index]
            patched = PeftModel.from_pretrained(hf_model, str(adapter_path))
            base[0].auto_model = patched  # type: ignore[index]
            self._lora_adapter_path = adapter_path
            log.info("dense_embedder.lora_loaded", adapter=str(adapter_path))
        except Exception as exc:
            raise EmbeddingError(f"LoRA adapter load failed: {exc}") from exc

    def set_projection(self, projection: QueryProjection) -> None:
        """Attach or replace the query projection layer.

        Args:
            projection: ``QueryProjection`` instance to use.
        """
        self._projection = projection
        log.info("dense_embedder.projection_set")

    @property
    def dimension(self) -> int:
        """Return embedding dimensionality (768 for nomic-embed-text-v1.5)."""
        return 768


class SparseEmbedder:
    """Wraps FastEmbed BM25 for sparse keyword embeddings.

    Returns ``qdrant_client.models.SparseVector`` objects directly, which
    can be passed to ``QdrantStore.upsert_chunks`` and ``hybrid_search``.
    """

    def __init__(self, model_name: str | None = None) -> None:
        """Initialise without loading the model (lazy load on first call).

        Args:
            model_name: FastEmbed sparse model ID. Defaults to settings value.
        """
        self._model_name = model_name or settings.sparse_embedding_model
        self._model: Any = None

    def _load_model(self) -> Any:
        """Load the FastEmbed sparse model (cached after first load)."""
        if self._model is None:
            import time

            from fastembed import SparseTextEmbedding

            t0 = time.monotonic()
            self._model = SparseTextEmbedding(
                model_name=self._model_name,
                cache_dir=str(settings.models_dir),
            )
            elapsed = round(time.monotonic() - t0, 2)
            log.info("sparse_embedder.loaded", model=self._model_name, elapsed_s=elapsed)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[SparseVector]:
        """Embed a batch of texts into BM25 sparse vectors.

        Args:
            texts: Texts to embed.

        Returns:
            List of ``SparseVector`` objects with indices and values as Python lists.

        Raises:
            EmbeddingError: On model or encoding failure.
        """
        if not texts:
            return []
        try:
            model = self._load_model()
            embeddings = await asyncio.to_thread(lambda: list(model.embed(texts)))
            return [
                SparseVector(indices=list(map(int, e.indices)), values=list(map(float, e.values)))
                for e in embeddings
            ]
        except Exception as exc:
            raise EmbeddingError(f"Sparse embedding failed: {exc}") from exc

    async def embed_query(self, query: str) -> SparseVector:
        """Embed a single query text.

        Args:
            query: Query text.

        Returns:
            ``SparseVector`` for the query.

        Raises:
            EmbeddingError: On model or encoding failure.
        """
        results = await self.embed_texts([query])
        if not results:
            raise EmbeddingError("Sparse query embedding returned empty result")
        return results[0]
