"""Unit tests for BenchmarkRunner (engagement graph mocked)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.benchmarks.models import MachineSpec, SolveOutcome
from seraph.benchmarks.runner import BenchmarkRunner, _make_run_id, _score_outcome

# ── Helpers ───────────────────────────────────────────────────────────────────


def _spec(
    name: str = "Lame",
    flags: dict[str, str] | None = None,
    expected_techniques: list[str] | None = None,
) -> MachineSpec:
    return MachineSpec(
        name=name,
        ip="10.10.10.3",
        os="Linux",
        difficulty="Easy",
        flags=flags or {"user": "<hash>", "root": "<hash>"},
        expected_techniques=expected_techniques or ["T1210"],
    )


def _fake_state(
    flags: list[str] | None = None,
    techniques: list[str] | None = None,
    kb_docs: int = 5,
    cited: int = 2,
    iteration: int = 3,
) -> MagicMock:
    state = MagicMock()
    state.flags = flags or []
    state.findings = []
    if techniques:
        finding = MagicMock()
        finding.mitre_techniques = techniques
        state.findings = [finding]
    state.kb_context = [MagicMock()] * kb_docs
    state.cited_doc_ids = [MagicMock()] * cited
    state.iteration = iteration
    return state


# ── Unit tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_machine_solved_no_real_flags() -> None:
    """Two flags with placeholder hashes → SOLVED (count-based)."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)
    fake_state = _fake_state(flags=["flag1", "flag2"])

    with patch.object(runner, "_invoke_graph", new=AsyncMock(return_value=fake_state)):
        result = await runner.run_machine(_spec())

    assert result.outcome == SolveOutcome.SOLVED
    assert len(result.flags_captured) == 2


@pytest.mark.asyncio
async def test_run_machine_partial_one_flag() -> None:
    """One flag with placeholder hashes → PARTIAL."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)
    fake_state = _fake_state(flags=["flag1"])

    with patch.object(runner, "_invoke_graph", new=AsyncMock(return_value=fake_state)):
        result = await runner.run_machine(_spec())

    assert result.outcome == SolveOutcome.PARTIAL


@pytest.mark.asyncio
async def test_run_machine_failed_no_flags() -> None:
    """No flags captured → FAILED."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)
    fake_state = _fake_state(flags=[])

    with patch.object(runner, "_invoke_graph", new=AsyncMock(return_value=fake_state)):
        result = await runner.run_machine(_spec())

    assert result.outcome == SolveOutcome.FAILED


@pytest.mark.asyncio
async def test_run_machine_timeout() -> None:
    """Graph exceeding timeout → SolveOutcome.TIMEOUT."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=1)

    async def _slow(_spec: MachineSpec) -> None:
        await asyncio.sleep(999)

    with patch.object(runner, "_invoke_graph", new=_slow):
        with patch("seraph.benchmarks.runner.asyncio.wait_for", side_effect=TimeoutError()):
            result = await runner.run_machine(_spec())

    assert result.outcome == SolveOutcome.TIMEOUT
    assert result.error == ""


@pytest.mark.asyncio
async def test_run_machine_exception_returns_error() -> None:
    """Unhandled exception from graph → SolveOutcome.ERROR with message."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)

    with patch.object(
        runner, "_invoke_graph", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        result = await runner.run_machine(_spec())

    assert result.outcome == SolveOutcome.ERROR
    assert "boom" in result.error


@pytest.mark.asyncio
async def test_run_machine_extracts_techniques() -> None:
    """Techniques are extracted from state.findings."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)
    fake_state = _fake_state(flags=["f1", "f2"], techniques=["T1210", "T1068"])

    with patch.object(runner, "_invoke_graph", new=AsyncMock(return_value=fake_state)):
        result = await runner.run_machine(_spec())

    assert "T1210" in result.techniques_used
    assert "T1068" in result.techniques_used


@pytest.mark.asyncio
async def test_run_machine_kb_utilization() -> None:
    """KB docs retrieved and cited are captured correctly."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)
    fake_state = _fake_state(flags=["f1"], kb_docs=10, cited=4)

    with patch.object(runner, "_invoke_graph", new=AsyncMock(return_value=fake_state)):
        result = await runner.run_machine(_spec())

    assert result.kb_docs_retrieved == 10
    assert result.kb_docs_cited == 4


@pytest.mark.asyncio
async def test_run_all_returns_report() -> None:
    """run_all returns a BenchmarkReport with one result per machine."""
    runner = BenchmarkRunner(api_key="test", timeout_seconds=60)
    fake_state = _fake_state(flags=["f1", "f2"])

    with patch.object(runner, "_invoke_graph", new=AsyncMock(return_value=fake_state)):
        report = await runner.run_all([_spec("Lame"), _spec("Blue")])

    assert len(report.results) == 2
    assert report.run_id.startswith("run-")


# ── score_outcome unit tests ──────────────────────────────────────────────────


def test_score_outcome_real_flags_solved() -> None:
    spec = _spec(flags={"user": "u123", "root": "r456"})
    assert _score_outcome(spec, ["u123", "r456"]) == SolveOutcome.SOLVED


def test_score_outcome_real_flags_partial() -> None:
    spec = _spec(flags={"user": "u123", "root": "r456"})
    assert _score_outcome(spec, ["u123"]) == SolveOutcome.PARTIAL


def test_score_outcome_real_flags_failed() -> None:
    spec = _spec(flags={"user": "u123", "root": "r456"})
    assert _score_outcome(spec, ["wrong"]) == SolveOutcome.FAILED


def test_make_run_id_format() -> None:
    run_id = _make_run_id()
    assert run_id.startswith("run-")
