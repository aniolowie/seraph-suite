"""Unit tests for benchmark Pydantic models."""

from __future__ import annotations

from seraph.benchmarks.models import (
    BenchmarkReport,
    BenchmarkResult,
    MachineSpec,
    SolveOutcome,
)


def _spec(name: str = "Lame", expected: list[str] | None = None) -> MachineSpec:
    return MachineSpec(
        name=name,
        ip="10.10.10.3",
        os="Linux",
        difficulty="Easy",
        flags={"user": "abc123", "root": "def456"},
        expected_techniques=expected or ["T1210", "T1068"],
    )


def _result(
    outcome: SolveOutcome = SolveOutcome.SOLVED,
    techniques: list[str] | None = None,
    retrieved: int = 10,
    cited: int = 5,
    flags: list[str] | None = None,
    time_to_root: float | None = 600.0,
) -> BenchmarkResult:
    return BenchmarkResult(
        machine=_spec(expected=["T1210", "T1068"]),
        outcome=outcome,
        flags_captured=flags or ["abc123", "def456"],
        time_to_root_seconds=time_to_root,
        total_time_seconds=620.0,
        techniques_used=techniques or ["T1210"],
        kb_docs_retrieved=retrieved,
        kb_docs_cited=cited,
    )


def test_machine_spec_has_real_flags() -> None:
    spec = _spec()
    assert spec.has_real_flags is True


def test_machine_spec_placeholder_flags() -> None:
    spec = MachineSpec(
        name="Lame", ip="10.10.10.3", flags={"user": "<hash>", "root": "<hash>"}
    )
    assert spec.has_real_flags is False


def test_benchmark_result_technique_accuracy_partial() -> None:
    r = _result(techniques=["T1210"])  # only 1 of 2 expected
    assert r.technique_accuracy == 0.5


def test_benchmark_result_technique_accuracy_full() -> None:
    r = _result(techniques=["T1210", "T1068"])
    assert r.technique_accuracy == 1.0


def test_benchmark_result_kb_utilization() -> None:
    r = _result(retrieved=10, cited=3)
    assert r.kb_utilization == 0.3


def test_benchmark_result_kb_utilization_zero_retrieved() -> None:
    r = _result(retrieved=0, cited=0)
    assert r.kb_utilization == 0.0


def test_benchmark_report_solve_rate() -> None:
    report = BenchmarkReport(
        run_id="test",
        results=[
            _result(outcome=SolveOutcome.SOLVED),
            _result(outcome=SolveOutcome.FAILED),
        ],
    )
    assert report.solve_rate == 0.5


def test_benchmark_report_avg_time_to_root_none_when_no_solves() -> None:
    report = BenchmarkReport(
        run_id="test",
        results=[_result(outcome=SolveOutcome.FAILED, time_to_root=None)],
    )
    assert report.avg_time_to_root_seconds is None


def test_benchmark_report_empty() -> None:
    report = BenchmarkReport(run_id="empty", results=[])
    assert report.solve_rate == 0.0
    assert report.avg_kb_utilization == 0.0
