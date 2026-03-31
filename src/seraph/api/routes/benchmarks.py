"""Benchmark history and trigger routes.

GET  /api/benchmarks              — list past runs
GET  /api/benchmarks/{run_id}     — single run detail
POST /api/benchmarks              — trigger a new run (async via Celery)
GET  /api/benchmarks/{run_id}/share — shareable static JSON
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException

from seraph.api.deps import MachineLoaderDep, SettingsDep
from seraph.api.schemas import (
    BenchmarkRunResponse,
    MachineResultResponse,
    TriggerBenchmarkRequest,
    TriggerBenchmarkResponse,
)
from seraph.benchmarks.models import BenchmarkReport

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


def _report_to_response(report: BenchmarkReport) -> BenchmarkRunResponse:
    results = [
        MachineResultResponse(
            name=r.machine.name,
            os=r.machine.os,
            difficulty=r.machine.difficulty,
            outcome=str(r.outcome),
            total_time_seconds=r.total_time_seconds,
            flags_captured=len(r.flags_captured),
            technique_accuracy=r.technique_accuracy,
            kb_utilization=r.kb_utilization,
            error=r.error,
        )
        for r in report.results
    ]
    return BenchmarkRunResponse(
        run_id=report.run_id,
        generated_at=report.generated_at,
        machine_count=len(report.results),
        solve_rate=report.solve_rate,
        partial_rate=report.partial_rate,
        avg_time_to_root_seconds=report.avg_time_to_root_seconds,
        avg_technique_accuracy=report.avg_technique_accuracy,
        avg_kb_utilization=report.avg_kb_utilization,
        results=results,
    )


def _load_reports(reports_dir: Path) -> list[BenchmarkReport]:
    """Scan ``reports_dir`` for JSON benchmark reports and parse them."""
    if not reports_dir.exists():
        return []
    reports: list[BenchmarkReport] = []
    for path in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            reports.append(BenchmarkReport.model_validate(data))
        except Exception as exc:
            log.warning("benchmarks.load_report_failed", path=str(path), error=str(exc))
    return reports


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[BenchmarkRunResponse], summary="List benchmark runs")
async def list_benchmarks(cfg: SettingsDep) -> list[BenchmarkRunResponse]:
    """Return all historical benchmark runs found in the reports directory."""
    reports = _load_reports(cfg.reports_dir)
    return [_report_to_response(r) for r in reports]


@router.get("/{run_id}", response_model=BenchmarkRunResponse, summary="Single run detail")
async def get_benchmark(run_id: str, cfg: SettingsDep) -> BenchmarkRunResponse:
    """Return the full result set for one benchmark run.

    Args:
        run_id: The run identifier (e.g. ``run-20250401-120000``).

    Raises:
        HTTPException: 404 if no matching report file is found.
    """
    report_path = cfg.reports_dir / f"{run_id}.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    try:
        data = json.loads(report_path.read_text())
        report = BenchmarkReport.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse report: {exc}") from exc
    return _report_to_response(report)


@router.post("", response_model=TriggerBenchmarkResponse, status_code=202, summary="Trigger run")
async def trigger_benchmark(
    body: TriggerBenchmarkRequest,
    cfg: SettingsDep,
    loader: MachineLoaderDep,
) -> TriggerBenchmarkResponse:
    """Enqueue a benchmark run via Celery and return immediately.

    Args:
        body: Which machines to run and per-machine timeout.

    Raises:
        HTTPException: 400 if no target is specified, 422 on validation errors.
    """
    if not body.machine and not body.difficulty and not body.run_all:
        raise HTTPException(
            status_code=400,
            detail="Specify at least one of: machine, difficulty, or run_all=true",
        )

    from seraph.benchmarks.runner import _make_run_id

    run_id = _make_run_id()

    try:
        from seraph.worker import run_benchmark_task

        task = run_benchmark_task.delay(
            machine=body.machine,
            difficulty=body.difficulty,
            run_all=body.run_all,
            timeout_seconds=body.timeout_seconds,
            run_id=run_id,
        )
        task_id = task.id
    except Exception as exc:
        log.warning("benchmarks.celery_unavailable", error=str(exc))
        # Celery not running — return the run_id so the caller knows the intent.
        task_id = f"direct-{run_id}"

    log.info("benchmarks.triggered", run_id=run_id, task_id=task_id)
    return TriggerBenchmarkResponse(run_id=run_id, task_id=task_id)


@router.get("/{run_id}/share", summary="Shareable static JSON")
async def share_benchmark(run_id: str, cfg: SettingsDep) -> dict:
    """Return the raw JSON payload for a run — suitable for sharing.

    Args:
        run_id: The run identifier.

    Raises:
        HTTPException: 404 if no matching report file is found.
    """
    report_path = cfg.reports_dir / f"{run_id}.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return json.loads(report_path.read_text())
