"""Query projection layer for LoRA-adapted retrieval.

Instead of re-embedding the entire corpus after LoRA training, we train a
lightweight 768→768 linear projection on top of the base embedder's query
output.  Only query vectors pass through the projection at inference time.

Architecture: Linear(768, 768, bias=False) → LayerNorm(768)

The trained projection is saved as a plain PyTorch state-dict (.pt file)
and loaded by DenseEmbedder on startup (or hot-reloaded after training).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from seraph.config import settings
from seraph.exceptions import ProjectionError

log = structlog.get_logger(__name__)

_DIM = 768


class QueryProjection:
    """768→768 linear+LayerNorm projection applied to query embeddings.

    Args:
        model_path: Path to the .pt state-dict file.  If the file does not
            exist, the projection is initialised as an identity mapping.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path or settings.projection_model_path
        self._model: Any = None  # torch.nn.Sequential

    def _build_model(self) -> Any:
        """Build the projection module (Linear + LayerNorm)."""
        import torch.nn as nn

        return nn.Sequential(
            nn.Linear(_DIM, _DIM, bias=False),
            nn.LayerNorm(_DIM),
        )

    def _load_or_init(self) -> Any:
        """Load weights from disk or initialise with identity-like values."""
        import torch

        model = self._build_model()
        if self._model_path.exists():
            try:
                state = torch.load(str(self._model_path), map_location="cpu", weights_only=True)
                model.load_state_dict(state)
                log.info("query_projection.loaded", path=str(self._model_path))
            except Exception as exc:
                log.warning("query_projection.load_failed", error=str(exc))
                _init_identity(model)
        else:
            _init_identity(model)
        model.eval()
        return model

    @property
    def model(self) -> Any:
        """Lazily load the projection model on first access."""
        if self._model is None:
            self._model = self._load_or_init()
        return self._model

    async def project(self, vector: list[float]) -> list[float]:
        """Apply the projection to a single query vector.

        Args:
            vector: 768-dimensional query embedding.

        Returns:
            Projected 768-dimensional vector (L2-normalised).

        Raises:
            ProjectionError: On shape mismatch or computation error.
        """
        try:
            result: list[float] = await asyncio.to_thread(self._project_sync, vector)
            return result
        except ProjectionError:
            raise
        except Exception as exc:
            raise ProjectionError(f"Projection failed: {exc}") from exc

    def _project_sync(self, vector: list[float]) -> list[float]:
        """Synchronous projection (runs in background thread)."""
        import torch
        import torch.nn.functional as F  # noqa: N812

        if len(vector) != _DIM:
            raise ProjectionError(f"Expected vector of dim {_DIM}, got {len(vector)}")
        with torch.no_grad():
            t = torch.tensor(vector, dtype=torch.float32).unsqueeze(0)
            out = self.model(t)
            out = F.normalize(out, dim=-1)
        return out.squeeze(0).tolist()

    async def save(self, path: Path | None = None) -> None:
        """Persist the current projection weights to disk.

        Args:
            path: Override save path (defaults to ``self._model_path``).

        Raises:
            ProjectionError: On save failure.
        """
        target = path or self._model_path
        try:
            import torch

            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(torch.save, self.model.state_dict(), str(target))
            log.info("query_projection.saved", path=str(target))
        except Exception as exc:
            raise ProjectionError(f"Failed to save projection: {exc}") from exc

    async def reload(self) -> None:
        """Hot-reload weights from disk without restarting the process.

        Raises:
            ProjectionError: If the file is missing or corrupt.
        """
        if not self._model_path.exists():
            raise ProjectionError(f"Projection file not found: {self._model_path}")
        try:
            import torch

            state = await asyncio.to_thread(torch.load, str(self._model_path), map_location="cpu")
            self.model.load_state_dict(state)
            self.model.eval()
            log.info("query_projection.reloaded", path=str(self._model_path))
        except Exception as exc:
            raise ProjectionError(f"Reload failed: {exc}") from exc


# ── Helpers ───────────────────────────────────────────────────────────────────


def _init_identity(model: Any) -> None:
    """Initialise Linear as identity and LayerNorm as pass-through."""
    import torch.nn as nn

    for m in model.modules():
        if isinstance(m, nn.Linear):
            nn.init.eye_(m.weight)
        elif isinstance(m, nn.LayerNorm):
            nn.init.ones_(m.weight)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
    log.info("query_projection.identity_init")
