"""Unit tests for ReportGenerator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seraph.benchmarks.models import BenchmarkReport, BenchmarkResult, MachineSpec, SolveOutcome
from seraph.benchmarks.report import ReportGenerator
from seraph.exceptions import BenchmarkError


def _spec(name: str = "Lame") -> MachineSpec:
    return MachineSpec(name=name, ip="10.10.10.3", os="Linux", difficulty="Easy")


def _result(
    name: str = "Lame",
    outcome: SolveOutcome = SolveOutcome.SOLVED,
) -> BenchmarkResult:
    return BenchmarkResult(
        machine=_spec(name),
        outcome=outcome,
        flags_captured=["f1", "f2"] if outcome == SolveOutcome.SOLVED else [],
        total_time_seconds=350.0,
        kb_docs_retrieved=8,
        kb_docs_cited=3,
    )


@pytest.fixture()
def report() -> BenchmarkReport:
    return BenchmarkReport(
        run_id="run-20250401",
        results=[
            _result("Lame", SolveOutcome.SOLVED),
            _result("Blue", SolveOutcome.FAILED),
        ],
    )


def test_to_markdown_contains_machine_names(report: BenchmarkReport) -> None:
    md = ReportGenerator().to_markdown(report)
    assert "Lame" in md
    assert "Blue" in md


def test_to_markdown_contains_run_id(report: BenchmarkReport) -> None:
    md = ReportGenerator().to_markdown(report)
    assert "run-20250401" in md


def test_to_json_round_trips(report: BenchmarkReport) -> None:
    gen = ReportGenerator()
    raw = gen.to_json(report)
    data = json.loads(raw)
    assert "summary" in data
    assert "results" in data
    assert data["summary"]["machine_count"] == 2
    assert data["summary"]["solve_rate"] == pytest.approx(0.5)


def test_save_writes_markdown(tmp_path: Path, report: BenchmarkReport) -> None:
    output = tmp_path / "reports" / "test.md"
    ReportGenerator().save(report, output, fmt="markdown")
    assert output.exists()
    content = output.read_text()
    assert "Lame" in content


def test_save_writes_json(tmp_path: Path, report: BenchmarkReport) -> None:
    output = tmp_path / "test.json"
    ReportGenerator().save(report, output, fmt="json")
    data = json.loads(output.read_text())
    assert "summary" in data


def test_save_unknown_format_raises(tmp_path: Path, report: BenchmarkReport) -> None:
    with pytest.raises(BenchmarkError, match="Unknown report format"):
        ReportGenerator().save(report, tmp_path / "out.txt", fmt="xml")


def test_zero_solve_report_markdown() -> None:
    report = BenchmarkReport(
        run_id="empty",
        results=[_result("Lame", SolveOutcome.FAILED)],
    )
    md = ReportGenerator().to_markdown(report)
    assert "0.0%" in md or "0%" in md
