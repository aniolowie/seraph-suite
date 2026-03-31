"""Celery beat task for periodic LoRA fine-tuning.

Runs every ``settings.training_schedule_hours`` hours.  If enough pending
triplets exist (≥ ``settings.min_triplets_for_training``), triggers a
training run and reloads the query projection.

The beat schedule is registered in ``celery_app.conf.beat_schedule``.
"""

from __future__ import annotations

import asyncio

import structlog

from seraph.config import settings
from seraph.exceptions import FinetuneError, SchedulerError
from seraph.worker import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(name="learning.trigger_training", bind=True, max_retries=2)
def task_trigger_training(self: object) -> dict[str, object]:  # type: ignore[override]
    """Celery beat task: check triplet count and trigger LoRA training if ready.

    Returns:
        Dict with keys: ``triggered`` (bool), ``triplets`` (int),
        ``adapter_path`` (str or None).

    Raises:
        SchedulerError: If the training check itself fails.
    """
    try:
        result = asyncio.run(_run_training_if_ready())
        log.info("scheduler.task_done", **result)
        return result
    except SchedulerError:
        raise
    except Exception as exc:
        log.error("scheduler.task_failed", error=str(exc))
        raise SchedulerError(f"Training scheduler failed: {exc}") from exc


async def _run_training_if_ready() -> dict[str, object]:
    """Check pending triplets and run training if threshold is met."""
    from seraph.learning.feedback import FeedbackDB
    from seraph.learning.finetune import LoRAFineTuner

    db = FeedbackDB()
    await db.initialize_schema()

    stats = await db.get_stats()
    pending = stats.get("pending_triplets", 0)

    log.info(
        "scheduler.check",
        pending_triplets=pending,
        threshold=settings.min_triplets_for_training,
    )

    if pending < settings.min_triplets_for_training:
        return {"triggered": False, "triplets": pending, "adapter_path": None}

    # Fetch triplets
    rows = await db.get_pending_triplets(limit=pending)
    triplet_dicts = [
        {
            "query": r["query"],
            "positive_text": r["positive_text"],
            "negative_text": r["negative_text"],
        }
        for r in rows
    ]
    triplet_ids = [r["id"] for r in rows]

    try:
        tuner = LoRAFineTuner()
        training_result = await tuner.train(triplet_dicts)
    except FinetuneError as exc:
        log.error("scheduler.training_failed", error=str(exc))
        return {"triggered": True, "triplets": pending, "adapter_path": None}

    # Mark triplets as used
    await db.mark_triplets_used(triplet_ids)

    # Save projection if it exists
    adapter_path = str(training_result.adapter_path)
    log.info(
        "scheduler.training_complete",
        adapter=adapter_path,
        loss=training_result.final_loss,
        duration_s=training_result.duration_seconds,
    )

    return {
        "triggered": True,
        "triplets": len(triplet_ids),
        "adapter_path": adapter_path,
        "final_loss": training_result.final_loss,
    }


# ── Register beat schedule ────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "seraph-lora-training": {
        "task": "learning.trigger_training",
        "schedule": settings.training_schedule_hours * 3600,  # seconds
    },
}
