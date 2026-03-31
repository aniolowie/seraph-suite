"""HTB engagement runner for the benchmarking harness.

Builds a Seraph engagement graph for each machine spec, invokes it
with a hard timeout, and evaluates the result into a ``BenchmarkResult``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from seraph.benchmarks.models import BenchmarkReport, BenchmarkResult, MachineSpec, SolveOutcome
from seraph.exceptions import EngagementRunError

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

# Placeholder sentinel used in machines.yaml when real flags are unknown.
_FLAG_PLACEHOLDER = "<hash>"


class BenchmarkRunner:
    """Runs HTB machine engagements and collects benchmark results.

    Builds one LangGraph engagement per machine, invokes it with a
    configurable timeout, then scores the outcome against known flags.

    Args:
        api_key: Anthropic API key.
        timeout_seconds: Per-machine wall-clock timeout (default 3600 s).
        machines_yaml_path: Optional override for the machines YAML location.
    """

    def __init__(
        self,
        api_key: str = "",
        timeout_seconds: int = 3600,
        machines_yaml_path: Path | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._machines_yaml_path = machines_yaml_path

    async def run_machine(self, spec: MachineSpec) -> BenchmarkResult:
        """Run a full engagement against a single machine.

        Args:
            spec: The machine definition (IP, expected flags, techniques).

        Returns:
            Populated ``BenchmarkResult``.
        """
        log.info(
            "benchmark.runner.start",
            machine=spec.name,
            ip=spec.ip,
            timeout=self._timeout,
        )
        started_at = datetime.now(UTC)
        wall_start = time.monotonic()

        try:
            final_state = await asyncio.wait_for(
                self._invoke_graph(spec),
                timeout=float(self._timeout),
            )
        except TimeoutError:
            total = time.monotonic() - wall_start
            log.warning("benchmark.runner.timeout", machine=spec.name, elapsed=total)
            return BenchmarkResult(
                machine=spec,
                outcome=SolveOutcome.TIMEOUT,
                total_time_seconds=round(total, 2),
                started_at=started_at,
            )
        except Exception as exc:
            total = time.monotonic() - wall_start
            log.error(
                "benchmark.runner.error",
                machine=spec.name,
                error=str(exc),
            )
            return BenchmarkResult(
                machine=spec,
                outcome=SolveOutcome.ERROR,
                total_time_seconds=round(total, 2),
                error=str(exc),
                started_at=started_at,
            )

        total = time.monotonic() - wall_start
        return self._evaluate(spec, final_state, total_seconds=total, started_at=started_at)

    async def run_all(
        self,
        specs: list[MachineSpec],
        run_id: str | None = None,
    ) -> BenchmarkReport:
        """Run engagements sequentially for every machine in ``specs``.

        Args:
            specs: Machines to benchmark.
            run_id: Optional identifier for the run; defaults to a timestamp UUID.

        Returns:
            ``BenchmarkReport`` with all results aggregated.
        """
        resolved_run_id = run_id or _make_run_id()
        log.info(
            "benchmark.runner.run_all",
            run_id=resolved_run_id,
            machine_count=len(specs),
        )
        results: list[BenchmarkResult] = []
        for spec in specs:
            result = await self.run_machine(spec)
            results.append(result)
            log.info(
                "benchmark.runner.machine_done",
                machine=spec.name,
                outcome=result.outcome,
                time=round(result.total_time_seconds, 1),
            )

        return BenchmarkReport(
            run_id=resolved_run_id,
            results=results,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _invoke_graph(self, spec: MachineSpec) -> object:
        """Build and invoke the LangGraph engagement for ``spec``.

        Returns:
            Final ``EngagementState`` after the graph completes.

        Raises:
            EngagementRunError: If the graph raises an unhandled exception.
        """
        from seraph.agents.graph_builder import build_engagement_graph
        from seraph.agents.state import EngagementState, Phase, TargetInfo
        from seraph.config import settings

        api_key = self._api_key or getattr(settings, "anthropic_api_key", "")
        graph = build_engagement_graph(
            api_key=api_key,
            engagement_id=f"bench-{spec.name}-{uuid.uuid4().hex[:8]}",
        )

        initial_state = EngagementState(
            target=TargetInfo(ip=spec.ip, os=spec.os),
            phase=Phase.RECON,
        )

        try:
            return await graph.ainvoke(initial_state)
        except Exception as exc:
            raise EngagementRunError(
                f"Graph invocation failed for {spec.name}: {exc}"
            ) from exc

    def _evaluate(
        self,
        spec: MachineSpec,
        state: object,
        total_seconds: float,
        started_at: datetime,
    ) -> BenchmarkResult:
        """Score an engagement state against the machine spec.

        Args:
            spec: Machine definition with expected flags and techniques.
            state: Final ``EngagementState`` from the graph.
            total_seconds: Wall-clock time for the engagement.
            started_at: When the engagement started (UTC).

        Returns:
            Populated ``BenchmarkResult``.
        """
        flags_captured: list[str] = list(getattr(state, "flags", []))
        findings = list(getattr(state, "findings", []))
        kb_context = list(getattr(state, "kb_context", []))
        cited_ids = list(getattr(state, "cited_doc_ids", []))
        iteration_count: int = int(getattr(state, "iteration", 0))

        # Technique IDs from all findings.
        techniques_used: list[str] = []
        for finding in findings:
            techniques_used.extend(getattr(finding, "mitre_techniques", []))
        techniques_used = list(dict.fromkeys(techniques_used))  # deduplicate, preserve order

        # Timing heuristics: flag timestamps aren't tracked, so we approximate.
        # user flag = first captured, root = second (or last).
        time_to_first: float | None = None
        time_to_root: float | None = None
        if flags_captured:
            # Without per-flag timestamps, we can't split precisely.
            # Use total time as proxy; real splits would need state augmentation.
            time_to_first = total_seconds
            if len(flags_captured) >= 2:
                time_to_root = total_seconds

        # Outcome: compare against spec flags when real hashes are available.
        outcome = _score_outcome(spec, flags_captured)

        return BenchmarkResult(
            machine=spec,
            outcome=outcome,
            flags_captured=flags_captured,
            time_to_first_flag_seconds=round(time_to_first, 2) if time_to_first else None,
            time_to_root_seconds=round(time_to_root, 2) if time_to_root else None,
            total_time_seconds=round(total_seconds, 2),
            techniques_used=techniques_used,
            kb_docs_retrieved=len(kb_context),
            kb_docs_cited=len(cited_ids),
            iteration_count=iteration_count,
            started_at=started_at,
        )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _score_outcome(spec: MachineSpec, flags_captured: list[str]) -> SolveOutcome:
    """Determine the solve outcome from captured flags.

    If real flag hashes are present in ``spec.flags``, validate captured
    strings against them.  Otherwise fall back to count-based scoring.
    """
    if not flags_captured:
        return SolveOutcome.FAILED

    if spec.has_real_flags:
        expected_values = {v for v in spec.flags.values() if v != _FLAG_PLACEHOLDER}
        matched = {f for f in flags_captured if f in expected_values}
        root_value = spec.flags.get("root", "")
        if root_value and root_value != _FLAG_PLACEHOLDER and root_value in matched:
            return SolveOutcome.SOLVED
        if matched:
            return SolveOutcome.PARTIAL
        return SolveOutcome.FAILED

    # No real hashes: score by count (>=2 flags = solved, 1 = partial).
    if len(flags_captured) >= 2:
        return SolveOutcome.SOLVED
    return SolveOutcome.PARTIAL


def _make_run_id() -> str:
    """Generate a human-readable run ID from current UTC time."""
    return datetime.now(UTC).strftime("run-%Y%m%d-%H%M%S")
