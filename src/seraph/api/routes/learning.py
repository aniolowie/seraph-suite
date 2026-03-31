"""Self-learning loop status routes.

GET /api/learning/stats           — feedback count, triplet count, training status
GET /api/learning/training-history — list of past LoRA training runs
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from fastapi import APIRouter

from seraph.api.deps import FeedbackDBDep, SettingsDep
from seraph.api.schemas import LearningStatsResponse, TrainingResultResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])

_TRAINING_HISTORY_FILE = "training_history.json"


def _load_training_history(adapter_dir: Path) -> list[TrainingResultResponse]:
    """Load past training results from a JSON history file in ``adapter_dir``.

    Args:
        adapter_dir: Directory where LoRA adapters and history are stored.

    Returns:
        List of TrainingResultResponse ordered newest first.
    """
    history_path = adapter_dir / _TRAINING_HISTORY_FILE
    if not history_path.exists():
        return []
    try:
        raw = json.loads(history_path.read_text())
        results = [TrainingResultResponse.model_validate(entry) for entry in raw]
        return sorted(results, key=lambda r: r.timestamp, reverse=True)
    except Exception as exc:
        log.warning("learning.history_load_failed", error=str(exc))
        return []


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/stats", response_model=LearningStatsResponse, summary="Learning loop stats")
async def learning_stats(cfg: SettingsDep, feedback_db: FeedbackDBDep) -> LearningStatsResponse:
    """Return feedback record count, triplet count, and last training result.

    A ``ready_to_train`` flag signals whether enough triplets are
    available for the next LoRA run.
    """
    try:
        stats = await feedback_db.get_stats()  # type: ignore[attr-defined]
        feedback_records = stats.get("total_records", 0)
        triplets_total = stats.get("pending_triplets", 0) + stats.get("used_triplets", 0)
    except Exception as exc:
        log.warning("learning.stats_failed", error=str(exc))
        feedback_records = 0
        triplets_total = 0

    history = _load_training_history(cfg.lora_adapter_dir)
    last_training = history[0] if history else None

    # Triplets pending = total triplets not yet used in any training run.
    triplets_used = last_training.triplets_used if last_training else 0
    triplets_pending = max(0, triplets_total - triplets_used)

    return LearningStatsResponse(
        feedback_records=feedback_records,
        triplets_total=triplets_total,
        triplets_pending=triplets_pending,
        min_triplets_required=cfg.min_triplets_for_training,
        ready_to_train=triplets_pending >= cfg.min_triplets_for_training,
        last_training=last_training,
        training_history=history,
    )


@router.get(
    "/training-history",
    response_model=list[TrainingResultResponse],
    summary="Training run history",
)
async def training_history(cfg: SettingsDep) -> list[TrainingResultResponse]:
    """Return the full list of past LoRA training runs, newest first."""
    return _load_training_history(cfg.lora_adapter_dir)
