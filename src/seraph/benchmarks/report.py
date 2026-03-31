"""Report generation for benchmark results.

Renders ``BenchmarkReport`` objects to markdown or JSON and writes them
to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from seraph.benchmarks.metrics import summary_dict
from seraph.benchmarks.models import BenchmarkReport, BenchmarkResult, SolveOutcome
from seraph.exceptions import BenchmarkError

log = structlog.get_logger(__name__)

# Outcome emoji mapping for markdown tables.
_OUTCOME_ICON: dict[SolveOutcome, str] = {
    SolveOutcome.SOLVED: "✅",
    SolveOutcome.PARTIAL: "🟡",
    SolveOutcome.FAILED: "❌",
    SolveOutcome.TIMEOUT: "⏱️",
    SolveOutcome.ERROR: "💥",
}


class ReportGenerator:
    """Renders and persists benchmark reports.

    Usage::

        gen = ReportGenerator()
        md = gen.to_markdown(report)
        gen.save(report, Path("reports/run-20250401.md"))
    """

    def to_markdown(self, report: BenchmarkReport) -> str:
        """Render a human-readable markdown report.

        Args:
            report: Completed benchmark report.

        Returns:
            Markdown string.
        """
        lines: list[str] = [
            f"# Seraph Benchmark Report — {report.run_id}",
            "",
            f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Machines:** {len(report.results)}  ",
            f"**Solve rate:** {report.solve_rate:.1%}  ",
            f"**Partial rate:** {report.partial_rate:.1%}  ",
        ]

        avg_root = report.avg_time_to_root_seconds
        if avg_root is not None:
            lines.append(f"**Avg time-to-root:** {avg_root:.0f}s  ")
        lines.append(f"**Avg technique accuracy:** {report.avg_technique_accuracy:.1%}  ")
        lines.append(f"**Avg KB utilization:** {report.avg_kb_utilization:.1%}  ")
        lines.append("")

        # Per-machine table
        lines += [
            "## Results",
            "",
            "| Machine | OS | Difficulty | Outcome | Time (s) | Flags | Techniques | KB util |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in report.results:
            icon = _OUTCOME_ICON.get(r.outcome, "?")
            time_str = f"{r.total_time_seconds:.0f}"
            flags_str = str(len(r.flags_captured))
            tech_str = f"{r.technique_accuracy:.0%}"
            kb_str = f"{r.kb_utilization:.0%}"
            lines.append(
                f"| {r.machine.name} | {r.machine.os} | {r.machine.difficulty} "
                f"| {icon} {r.outcome} | {time_str} | {flags_str} "
                f"| {tech_str} | {kb_str} |"
            )

        # Error details
        errors = [r for r in report.results if r.error]
        if errors:
            lines += ["", "## Errors", ""]
            for r in errors:
                lines.append(f"**{r.machine.name}**: {r.error}")

        lines.append("")
        return "\n".join(lines)

    def to_json(self, report: BenchmarkReport) -> str:
        """Serialise the report to a JSON string.

        Includes both raw results and computed summary metrics.

        Args:
            report: Completed benchmark report.

        Returns:
            JSON string (2-space indented).
        """
        payload = {
            "summary": summary_dict(report),
            "results": [_result_to_dict(r) for r in report.results],
        }
        return json.dumps(payload, indent=2, default=str)

    def save(
        self,
        report: BenchmarkReport,
        path: Path,
        fmt: str = "markdown",
    ) -> None:
        """Write the report to a file.

        Args:
            report: Completed benchmark report.
            path: Output file path (parent dirs are created automatically).
            fmt: ``"markdown"`` (default) or ``"json"``.

        Raises:
            BenchmarkError: If ``fmt`` is not recognised or write fails.
        """
        if fmt not in ("markdown", "json"):
            raise BenchmarkError(f"Unknown report format {fmt!r}. Use 'markdown' or 'json'.")

        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.to_markdown(report) if fmt == "markdown" else self.to_json(report)
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise BenchmarkError(f"Failed to write report to {path}: {exc}") from exc

        log.info("benchmark.report.saved", path=str(path), fmt=fmt)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _result_to_dict(r: BenchmarkResult) -> dict[str, object]:
    """Flatten a BenchmarkResult to a plain dict for JSON output."""
    return {
        "machine": r.machine.name,
        "ip": r.machine.ip,
        "os": r.machine.os,
        "difficulty": r.machine.difficulty,
        "outcome": r.outcome,
        "flags_captured": r.flags_captured,
        "time_to_first_flag_seconds": r.time_to_first_flag_seconds,
        "time_to_root_seconds": r.time_to_root_seconds,
        "total_time_seconds": r.total_time_seconds,
        "techniques_used": r.techniques_used,
        "kb_docs_retrieved": r.kb_docs_retrieved,
        "kb_docs_cited": r.kb_docs_cited,
        "iteration_count": r.iteration_count,
        "technique_accuracy": round(r.technique_accuracy, 3),
        "kb_utilization": round(r.kb_utilization, 3),
        "error": r.error,
        "started_at": r.started_at.isoformat(),
    }
