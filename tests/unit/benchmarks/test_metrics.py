"""Unit tests for benchmarks/metrics.py."""

from __future__ import annotations

from seraph.benchmarks.metrics import (
    avg_time_to_root,
    kb_utilization,
    learning_curve,
    partial_rate,
    solve_rate,
    summary_dict,
    technique_accuracy,
)
from seraph.benchmarks.models import BenchmarkReport, BenchmarkResult, MachineSpec, SolveOutcome


def _spec(expected: list[str] | None = None) -> MachineSpec:
    return MachineSpec(
        name="Test",
        ip="10.0.0.1",
        expected_techniques=expected or ["T1210"],
    )


def _result(
    outcome: SolveOutcome = SolveOutcome.SOLVED,
    time_to_root: float | None = 300.0,
    techniques: list[str] | None = None,
    retrieved: int = 10,
    cited: int = 5,
    spec: MachineSpec | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        machine=spec or _spec(),
        outcome=outcome,
        flags_captured=["f1", "f2"] if outcome == SolveOutcome.SOLVED else [],
        time_to_root_seconds=time_to_root,
        total_time_seconds=320.0,
        techniques_used=techniques or ["T1210"],
        kb_docs_retrieved=retrieved,
        kb_docs_cited=cited,
    )


def test_solve_rate_all_solved() -> None:
    results = [_result(SolveOutcome.SOLVED), _result(SolveOutcome.SOLVED)]
    assert solve_rate(results) == 1.0


def test_solve_rate_none_solved() -> None:
    results = [_result(SolveOutcome.FAILED), _result(SolveOutcome.TIMEOUT)]
    assert solve_rate(results) == 0.0


def test_solve_rate_empty() -> None:
    assert solve_rate([]) == 0.0


def test_partial_rate_includes_partial_and_solved() -> None:
    results = [
        _result(SolveOutcome.SOLVED),
        _result(SolveOutcome.PARTIAL),
        _result(SolveOutcome.FAILED),
    ]
    assert partial_rate(results) == pytest.approx(2 / 3)


def test_avg_time_to_root_mean() -> None:
    results = [
        _result(SolveOutcome.SOLVED, time_to_root=200.0),
        _result(SolveOutcome.SOLVED, time_to_root=400.0),
    ]
    assert avg_time_to_root(results) == pytest.approx(300.0)


def test_avg_time_to_root_none_when_no_solves() -> None:
    results = [_result(SolveOutcome.FAILED, time_to_root=None)]
    assert avg_time_to_root(results) is None


def test_technique_accuracy_partial() -> None:
    spec = _spec(expected=["T1210", "T1068"])
    results = [_result(techniques=["T1210"], spec=spec)]
    assert technique_accuracy(results) == pytest.approx(0.5)


def test_kb_utilization_mean() -> None:
    results = [
        _result(retrieved=10, cited=5),
        _result(retrieved=10, cited=2),
    ]
    assert kb_utilization(results) == pytest.approx(0.35)


def test_learning_curve_monotonic_growth() -> None:
    results = [
        _result(SolveOutcome.SOLVED),
        _result(SolveOutcome.FAILED),
        _result(SolveOutcome.SOLVED),
    ]
    curve = learning_curve(results)
    assert len(curve) == 3
    assert curve[0] == pytest.approx(1.0)
    assert curve[1] == pytest.approx(0.5)
    assert curve[2] == pytest.approx(2 / 3)


def test_summary_dict_keys() -> None:
    report = BenchmarkReport(run_id="r1", results=[_result()])
    s = summary_dict(report)
    assert "solve_rate" in s
    assert "technique_accuracy" in s
    assert "kb_utilization" in s
    assert s["machine_count"] == 1


import pytest  # noqa: E402 (must be after test functions that use it)
