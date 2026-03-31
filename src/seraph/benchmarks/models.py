"""Pydantic models for the HTB benchmarking harness.

All models are immutable by convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class SolveOutcome(StrEnum):
    """Result of a single machine engagement."""

    SOLVED = "solved"    # both user + root flags captured
    PARTIAL = "partial"  # user flag only
    FAILED = "failed"    # no flags captured within time limit
    TIMEOUT = "timeout"  # engagement exceeded the configured timeout
    ERROR = "error"      # unhandled exception during engagement


class MachineSpec(BaseModel):
    """Definition of a single HTB machine used as a benchmark target.

    Loaded from ``tests/benchmarks/machines.yaml``.
    """

    name: str = Field(description="HTB machine name, e.g. 'Lame'.")
    ip: str = Field(description="Machine IP address on the HTB VPN.")
    os: str = Field(default="", description="Operating system: 'Linux' or 'Windows'.")
    difficulty: Literal["Easy", "Medium", "Hard", "Insane"] = "Easy"
    flags: dict[str, str] = Field(
        default_factory=dict,
        description="Flag hashes: {'user': '<hash>', 'root': '<hash>'}. "
        "Use placeholder '<hash>' to skip hash validation.",
    )
    expected_techniques: list[str] = Field(
        default_factory=list,
        description="MITRE ATT&CK technique IDs expected for optimal solution.",
    )

    @property
    def has_real_flags(self) -> bool:
        """True when at least one flag is a non-placeholder hash."""
        return any(v != "<hash>" and v for v in self.flags.values())


class BenchmarkResult(BaseModel):
    """Outcome of running a single machine engagement.

    Populated by ``BenchmarkRunner.run_machine()``.
    """

    machine: MachineSpec
    outcome: SolveOutcome
    flags_captured: list[str] = Field(default_factory=list)
    time_to_first_flag_seconds: float | None = None
    time_to_root_seconds: float | None = None
    total_time_seconds: float = 0.0
    techniques_used: list[str] = Field(
        default_factory=list,
        description="MITRE T-IDs extracted from state.findings.",
    )
    kb_docs_retrieved: int = 0
    kb_docs_cited: int = 0
    iteration_count: int = 0
    error: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def technique_accuracy(self) -> float:
        """Fraction of expected techniques that were actually used (0-1).

        Returns 0.0 when no expected techniques are defined.
        """
        expected = self.machine.expected_techniques
        if not expected:
            return 0.0
        used = set(self.techniques_used)
        return sum(1 for t in expected if t in used) / len(expected)

    @property
    def kb_utilization(self) -> float:
        """Fraction of retrieved KB docs that were cited by the LLM (0-1).

        Returns 0.0 when nothing was retrieved.
        """
        if self.kb_docs_retrieved == 0:
            return 0.0
        return min(self.kb_docs_cited / self.kb_docs_retrieved, 1.0)


class BenchmarkReport(BaseModel):
    """Aggregated results of a benchmarking run over multiple machines."""

    run_id: str = Field(description="Unique identifier for this run (e.g. ISO timestamp).")
    results: list[BenchmarkResult] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ── Computed aggregates ───────────────────────────────────────────────────

    @computed_field  # type: ignore[misc]
    @property
    def solve_rate(self) -> float:
        """Fraction of machines with SOLVED outcome (0-1)."""
        if not self.results:
            return 0.0
        solved = sum(1 for r in self.results if r.outcome == SolveOutcome.SOLVED)
        return solved / len(self.results)

    @computed_field  # type: ignore[misc]
    @property
    def partial_rate(self) -> float:
        """Fraction of machines with at least one flag captured (0-1)."""
        if not self.results:
            return 0.0
        partial = sum(
            1
            for r in self.results
            if r.outcome in (SolveOutcome.SOLVED, SolveOutcome.PARTIAL)
        )
        return partial / len(self.results)

    @computed_field  # type: ignore[misc]
    @property
    def avg_time_to_root_seconds(self) -> float | None:
        """Average time-to-root across all SOLVED machines, or None."""
        times = [
            r.time_to_root_seconds
            for r in self.results
            if r.outcome == SolveOutcome.SOLVED and r.time_to_root_seconds is not None
        ]
        return sum(times) / len(times) if times else None

    @computed_field  # type: ignore[misc]
    @property
    def avg_technique_accuracy(self) -> float:
        """Mean technique accuracy across all results."""
        if not self.results:
            return 0.0
        return sum(r.technique_accuracy for r in self.results) / len(self.results)

    @computed_field  # type: ignore[misc]
    @property
    def avg_kb_utilization(self) -> float:
        """Mean KB utilization across all results."""
        if not self.results:
            return 0.0
        return sum(r.kb_utilization for r in self.results) / len(self.results)
