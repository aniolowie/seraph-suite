"""Unit tests for API Pydantic schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from seraph.api.schemas import (
    BenchmarkRunResponse,
    CollectionStats,
    EngagementDetail,
    EngagementSummary,
    ErrorResponse,
    HealthResponse,
    IngestionSourceStatus,
    LearningStatsResponse,
    MachineCreateRequest,
    MachineResponse,
    MachineResultResponse,
    ServiceStatus,
    TrainingResultResponse,
    TriggerBenchmarkRequest,
    WriteupSubmitResponse,
    WriteupTaskStatus,
)


# ── HealthResponse ────────────────────────────────────────────────────────────


def test_health_response_ok() -> None:
    h = HealthResponse(status="ok")
    assert h.status == "ok"
    assert h.services == []


def test_health_response_with_services() -> None:
    h = HealthResponse(
        status="degraded",
        services=[ServiceStatus(name="qdrant", ok=False, detail="connection refused")],
    )
    assert len(h.services) == 1
    assert not h.services[0].ok


# ── EngagementSummary / EngagementDetail ──────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


def test_engagement_summary_defaults() -> None:
    s = EngagementSummary(
        engagement_id="bench-lame-abc",
        target_ip="10.10.10.3",
        phase="recon",
        started_at=_now(),
    )
    assert s.flags_captured == 0
    assert s.findings_count == 0
    assert s.target_os == ""


def test_engagement_detail_extends_summary() -> None:
    d = EngagementDetail(
        engagement_id="bench-lame-abc",
        target_ip="10.10.10.3",
        phase="exploit",
        started_at=_now(),
        findings=[{"type": "open_port", "port": 445}],
    )
    assert len(d.findings) == 1
    assert d.tool_outputs == []


# ── BenchmarkRunResponse ──────────────────────────────────────────────────────


def test_benchmark_run_response_serialises() -> None:
    result = MachineResultResponse(
        name="Lame",
        os="Linux",
        difficulty="Easy",
        outcome="solved",
        total_time_seconds=1203.0,
        flags_captured=2,
        technique_accuracy=1.0,
        kb_utilization=0.6,
    )
    run = BenchmarkRunResponse(
        run_id="run-20250401-120000",
        generated_at=_now(),
        machine_count=1,
        solve_rate=1.0,
        partial_rate=1.0,
        avg_time_to_root_seconds=1203.0,
        avg_technique_accuracy=1.0,
        avg_kb_utilization=0.6,
        results=[result],
    )
    data = run.model_dump()
    assert data["run_id"] == "run-20250401-120000"
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Lame"


def test_benchmark_run_response_no_root_time() -> None:
    run = BenchmarkRunResponse(
        run_id="run-x",
        generated_at=_now(),
        machine_count=0,
        solve_rate=0.0,
        partial_rate=0.0,
        avg_time_to_root_seconds=None,
        avg_technique_accuracy=0.0,
        avg_kb_utilization=0.0,
    )
    assert run.avg_time_to_root_seconds is None


# ── TriggerBenchmarkRequest ───────────────────────────────────────────────────


def test_trigger_request_valid() -> None:
    r = TriggerBenchmarkRequest(machine="Lame", timeout_seconds=3600)
    assert r.machine == "Lame"
    assert not r.run_all


def test_trigger_request_timeout_bounds() -> None:
    with pytest.raises(ValidationError):
        TriggerBenchmarkRequest(run_all=True, timeout_seconds=10)  # below 60


# ── MachineCreateRequest ──────────────────────────────────────────────────────


def test_machine_create_valid() -> None:
    m = MachineCreateRequest(
        name="Lame",
        ip="10.10.10.3",
        os="Linux",
        difficulty="Easy",
        expected_techniques=["T1210"],
    )
    assert m.difficulty == "Easy"


def test_machine_create_invalid_difficulty() -> None:
    with pytest.raises(ValidationError):
        MachineCreateRequest(name="X", ip="10.0.0.1", os="Linux", difficulty="Trivial")


def test_machine_create_empty_name() -> None:
    with pytest.raises(ValidationError):
        MachineCreateRequest(name="", ip="10.0.0.1", os="Linux", difficulty="Easy")


# ── CollectionStats ───────────────────────────────────────────────────────────


def test_collection_stats_fields() -> None:
    c = CollectionStats(
        collection_name="seraph_kb",
        points_count=12345,
        vectors_count=12345,
        indexed=True,
        status="green",
    )
    assert c.indexed is True


# ── LearningStatsResponse ─────────────────────────────────────────────────────


def test_learning_stats_ready_flag() -> None:
    s = LearningStatsResponse(
        feedback_records=100,
        triplets_total=60,
        triplets_pending=60,
        min_triplets_required=50,
        ready_to_train=True,
    )
    assert s.ready_to_train is True
    assert s.last_training is None


def test_learning_stats_with_training() -> None:
    t = TrainingResultResponse(
        timestamp=_now(),
        triplets_used=55,
        final_loss=0.42,
        duration_seconds=120.0,
        adapter_path="/data/models/lora_adapters/latest",
        success=True,
    )
    s = LearningStatsResponse(
        feedback_records=200,
        triplets_total=110,
        triplets_pending=55,
        min_triplets_required=50,
        ready_to_train=True,
        last_training=t,
    )
    assert s.last_training is not None
    assert s.last_training.success is True


# ── WriteupSubmitResponse / WriteupTaskStatus ─────────────────────────────────


def test_writeup_submit_response() -> None:
    r = WriteupSubmitResponse(
        task_id="abc-123",
        filename="lame.md",
        status_url="/api/writeups/status/abc-123",
    )
    assert r.status == "accepted"


def test_writeup_task_status_unknown() -> None:
    s = WriteupTaskStatus(task_id="abc-123", state="PENDING")
    assert s.result is None
    assert s.error == ""


# ── ErrorResponse ─────────────────────────────────────────────────────────────


def test_error_response_serialises() -> None:
    e = ErrorResponse(error="NotFound", detail="machine not found", path="/api/machines/X")
    data = e.model_dump()
    assert data["error"] == "NotFound"
    assert data["path"] == "/api/machines/X"


# ── IngestionSourceStatus ─────────────────────────────────────────────────────


def test_ingestion_source_status_no_last_updated() -> None:
    s = IngestionSourceStatus(source="nvd", document_count=0, last_updated=None)
    assert s.last_updated is None
    assert not s.active
