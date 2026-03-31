"""Pydantic v2 request/response schemas for the Seraph FastAPI layer.

These are *API* models — they mirror internal domain models but are
intentionally separate so the public contract can evolve independently
of internal representations.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

# ── Health ────────────────────────────────────────────────────────────────────


class ServiceStatus(BaseModel):
    """Connectivity status for a single backing service."""

    name: str
    ok: bool
    detail: str = ""


class HealthResponse(BaseModel):
    """Response for GET /api/health and GET /api/readyz."""

    status: str  # "ok" | "degraded"
    services: list[ServiceStatus] = Field(default_factory=list)


# ── Engagements ───────────────────────────────────────────────────────────────


class EngagementSummary(BaseModel):
    """Compact representation of a running or recently completed engagement."""

    engagement_id: str
    target_ip: str
    target_os: str = ""
    phase: str  # recon | enumerate | exploit | privesc | post | done
    flags_captured: int = 0
    findings_count: int = 0
    elapsed_seconds: float = 0.0
    started_at: datetime


class EngagementDetail(EngagementSummary):
    """Full engagement state snapshot (single-engagement view)."""

    findings: list[dict] = Field(default_factory=list)
    tool_outputs: list[dict] = Field(default_factory=list)
    plan: list[dict] = Field(default_factory=list)


# ── Benchmarks ────────────────────────────────────────────────────────────────


class MachineResultResponse(BaseModel):
    """Per-machine result row in a benchmark run."""

    name: str
    os: str
    difficulty: str
    outcome: str
    total_time_seconds: float
    flags_captured: int
    technique_accuracy: float
    kb_utilization: float
    error: str = ""


class BenchmarkRunResponse(BaseModel):
    """Summary of a completed benchmark run."""

    run_id: str
    generated_at: datetime
    machine_count: int
    solve_rate: float
    partial_rate: float
    avg_time_to_root_seconds: float | None
    avg_technique_accuracy: float
    avg_kb_utilization: float
    results: list[MachineResultResponse] = Field(default_factory=list)


class TriggerBenchmarkRequest(BaseModel):
    """Body for POST /api/benchmarks — trigger a new run."""

    machine: str | None = Field(default=None, description="Single machine name.")
    difficulty: str | None = Field(
        default=None,
        description="Run all machines with this difficulty.",
    )
    run_all: bool = Field(default=False, description="Run every registered machine.")
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class TriggerBenchmarkResponse(BaseModel):
    """Accepted response for a newly triggered benchmark run."""

    run_id: str
    task_id: str
    status: str = "accepted"


# ── Knowledge base ────────────────────────────────────────────────────────────


class CollectionStats(BaseModel):
    """Qdrant collection metadata."""

    collection_name: str
    points_count: int
    vectors_count: int
    indexed: bool
    status: str  # "green" | "yellow" | "red"


class IngestionSourceStatus(BaseModel):
    """Per-source ingestion status from SQLite state."""

    source: str  # "nvd" | "exploitdb" | "mitre" | "writeups"
    document_count: int
    last_updated: datetime | None
    errors: int = 0
    active: bool = False  # True if a Celery task is currently running


class KnowledgeStatsResponse(BaseModel):
    """Combined KB stats response."""

    collection: CollectionStats
    ingestion: list[IngestionSourceStatus] = Field(default_factory=list)


# ── Learning loop ─────────────────────────────────────────────────────────────


class TrainingResultResponse(BaseModel):
    """API representation of a completed LoRA training run."""

    timestamp: datetime
    triplets_used: int
    final_loss: float
    duration_seconds: float
    adapter_path: str
    success: bool
    error_message: str = ""


class LearningStatsResponse(BaseModel):
    """Learning loop health metrics."""

    feedback_records: int
    triplets_total: int
    triplets_pending: int
    min_triplets_required: int
    ready_to_train: bool
    last_training: TrainingResultResponse | None = None
    training_history: list[TrainingResultResponse] = Field(default_factory=list)


# ── Machines ──────────────────────────────────────────────────────────────────


class MachineResponse(BaseModel):
    """API representation of a registered HTB machine."""

    name: str
    ip: str
    os: str
    difficulty: str
    expected_techniques: list[str] = Field(default_factory=list)
    has_real_flags: bool


class MachineCreateRequest(BaseModel):
    """Body for POST /api/machines."""

    name: str = Field(min_length=1, max_length=64)
    ip: str = Field(min_length=7, max_length=45)
    os: str = Field(min_length=1, max_length=32)
    difficulty: str = Field(pattern="^(Easy|Medium|Hard|Insane)$")
    expected_techniques: list[str] = Field(default_factory=list)


# ── Writeups ──────────────────────────────────────────────────────────────────


class WriteupSubmitResponse(BaseModel):
    """Accepted response for a writeup file upload."""

    task_id: str
    filename: str
    status: str = "accepted"
    status_url: str


class WriteupTaskStatus(BaseModel):
    """Celery task status for writeup ingestion."""

    task_id: str
    state: str  # PENDING | STARTED | SUCCESS | FAILURE
    result: dict | None = None
    error: str = ""


# ── Shared error envelope ─────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: str
    detail: str = ""
    path: str = ""


# ── Paths helper (for Path serialization) ────────────────────────────────────


def _path_str(p: Path | None) -> str | None:
    """Convert Path to string for JSON serialization."""
    return str(p) if p is not None else None
