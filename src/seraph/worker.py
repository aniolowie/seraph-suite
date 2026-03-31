"""Celery application factory for Seraph Suite.

Import ``celery_app`` in task modules and the CLI to dispatch/monitor tasks.

Start the worker with::

    celery -A seraph.worker worker --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from seraph.config import settings

celery_app = Celery(
    "seraph",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=86400,  # 24 hours
)

# Auto-discover tasks in seraph.ingestion.tasks and seraph.learning.scheduler
celery_app.autodiscover_tasks(["seraph.ingestion", "seraph.learning"])


@celery_app.task(name="seraph.worker.run_benchmark_task", bind=True)
def run_benchmark_task(
    self: object,
    machine: str | None = None,
    difficulty: str | None = None,
    run_all: bool = False,
    timeout_seconds: int = 3600,
    run_id: str | None = None,
) -> dict:
    """Run a benchmark engagement and save the report as JSON.

    Args:
        machine: Optional single machine name.
        difficulty: Optional difficulty filter.
        run_all: Run all registered machines.
        timeout_seconds: Per-machine timeout.
        run_id: Pre-assigned run ID (generated if None).

    Returns:
        Dict with ``run_id`` and ``solved`` count.
    """
    import asyncio

    from seraph.benchmarks.loader import MachineLoader
    from seraph.benchmarks.report import ReportGenerator
    from seraph.benchmarks.runner import BenchmarkRunner, _make_run_id

    resolved_run_id = run_id or _make_run_id()
    loader = MachineLoader()

    if machine:
        specs = [loader.load_by_name(machine)]
    elif difficulty:
        specs = loader.load_by_difficulty(difficulty)  # type: ignore[arg-type]
    else:
        specs = loader.load_all()

    runner = BenchmarkRunner(timeout_seconds=timeout_seconds)
    report = asyncio.run(runner.run_all(specs, run_id=resolved_run_id))

    gen = ReportGenerator()
    gen.save(report, settings.reports_dir / f"{resolved_run_id}.json", fmt="json")

    solved = sum(1 for r in report.results if str(r.outcome) == "solved")
    return {"run_id": resolved_run_id, "solved": solved, "total": len(report.results)}


@celery_app.task(name="seraph.worker.ingest_writeup_task", bind=True)
def ingest_writeup_task(self: object, file_path: str) -> dict:
    """Ingest a single writeup markdown file into the knowledge base.

    Args:
        file_path: Absolute path to the .md file.

    Returns:
        Dict with ``file`` and ``status``.
    """
    import asyncio
    from pathlib import Path

    from seraph.ingestion.writeups import WriteupIngestor

    ingestor = WriteupIngestor()
    p = Path(file_path)
    asyncio.run(ingestor.ingest(directory=p.parent, glob_pattern=p.name))
    return {"file": file_path, "status": "ingested"}
