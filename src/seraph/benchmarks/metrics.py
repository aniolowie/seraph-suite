"""Stateless metric helpers for benchmark reports.

All functions operate on ``BenchmarkReport`` or ``list[BenchmarkResult]``
and return plain Python scalars/lists — no side effects.
"""

from __future__ import annotations

from seraph.benchmarks.models import BenchmarkReport, BenchmarkResult, SolveOutcome


def solve_rate(results: list[BenchmarkResult]) -> float:
    """Fraction of machines where the root flag was captured.

    Args:
        results: List of benchmark results.

    Returns:
        Float in [0, 1]. Returns 0.0 for empty input.
    """
    if not results:
        return 0.0
    return sum(1 for r in results if r.outcome == SolveOutcome.SOLVED) / len(results)


def partial_rate(results: list[BenchmarkResult]) -> float:
    """Fraction of machines where at least one flag was captured.

    Args:
        results: List of benchmark results.

    Returns:
        Float in [0, 1].
    """
    if not results:
        return 0.0
    success = sum(
        1
        for r in results
        if r.outcome in (SolveOutcome.SOLVED, SolveOutcome.PARTIAL)
    )
    return success / len(results)


def avg_time_to_root(results: list[BenchmarkResult]) -> float | None:
    """Mean time-to-root in seconds across all SOLVED machines.

    Args:
        results: List of benchmark results.

    Returns:
        Mean seconds, or ``None`` if no machines were fully solved.
    """
    times = [
        r.time_to_root_seconds
        for r in results
        if r.outcome == SolveOutcome.SOLVED and r.time_to_root_seconds is not None
    ]
    return sum(times) / len(times) if times else None


def technique_accuracy(results: list[BenchmarkResult]) -> float:
    """Mean fraction of expected MITRE techniques that were used.

    Only machines with at least one expected technique contribute.

    Args:
        results: List of benchmark results.

    Returns:
        Float in [0, 1]. Returns 0.0 if no machines defined expected techniques.
    """
    scored = [r for r in results if r.machine.expected_techniques]
    if not scored:
        return 0.0
    return sum(r.technique_accuracy for r in scored) / len(scored)


def kb_utilization(results: list[BenchmarkResult]) -> float:
    """Mean fraction of retrieved KB docs that were cited.

    Args:
        results: List of benchmark results.

    Returns:
        Float in [0, 1]. Returns 0.0 if nothing was retrieved.
    """
    active = [r for r in results if r.kb_docs_retrieved > 0]
    if not active:
        return 0.0
    return sum(r.kb_utilization for r in active) / len(active)


def learning_curve(results: list[BenchmarkResult]) -> list[float]:
    """Per-machine cumulative solve rate (in run order).

    Useful for plotting how the solve rate improves over successive
    engagements within a single benchmarking run.

    Args:
        results: List of benchmark results in chronological order.

    Returns:
        List of floats where index ``i`` is the solve rate after the
        first ``i+1`` machines.
    """
    curve: list[float] = []
    solved_count = 0
    for i, result in enumerate(results):
        if result.outcome == SolveOutcome.SOLVED:
            solved_count += 1
        curve.append(solved_count / (i + 1))
    return curve


def summary_dict(report: BenchmarkReport) -> dict[str, object]:
    """Return a flat summary dict suitable for JSON serialisation or logging.

    Args:
        report: Completed benchmark report.

    Returns:
        Dict with scalar metric values.
    """
    results = report.results
    return {
        "run_id": report.run_id,
        "machine_count": len(results),
        "solve_rate": round(solve_rate(results), 3),
        "partial_rate": round(partial_rate(results), 3),
        "avg_time_to_root_seconds": avg_time_to_root(results),
        "technique_accuracy": round(technique_accuracy(results), 3),
        "kb_utilization": round(kb_utilization(results), 3),
        "learning_curve": learning_curve(results),
    }
