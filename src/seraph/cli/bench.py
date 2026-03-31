"""CLI command: ``seraph bench`` — run the HTB benchmarking harness.

Usage examples::

    seraph bench --machine Lame --timeout 3600
    seraph bench --difficulty Easy --all --report --output reports/easy.md
    seraph bench --all --report --output reports/full.json --format json
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import structlog

from seraph.benchmarks.loader import MachineLoader
from seraph.benchmarks.models import MachineSpec
from seraph.benchmarks.report import ReportGenerator
from seraph.benchmarks.runner import BenchmarkRunner
from seraph.exceptions import BenchmarkError, MachineLoadError

log = structlog.get_logger(__name__)


@click.command(name="bench")
@click.option("--machine", "-m", default=None, help="HTB machine name (case-insensitive).")
@click.option(
    "--difficulty",
    type=click.Choice(["Easy", "Medium", "Hard", "Insane"]),
    default=None,
    help="Filter machines by difficulty.",
)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    default=False,
    help="Run every machine in machines.yaml.",
)
@click.option(
    "--timeout",
    type=int,
    default=3600,
    show_default=True,
    help="Per-machine timeout in seconds.",
)
@click.option(
    "--report",
    is_flag=True,
    default=False,
    help="Print a summary report after all machines complete.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Save report to this file path.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
    help="Report output format.",
)
@click.option(
    "--machines-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to machines.yaml (default: tests/benchmarks/machines.yaml).",
)
@click.pass_context
def bench(
    ctx: click.Context,
    machine: str | None,
    difficulty: str | None,
    run_all: bool,
    timeout: int,
    report: bool,
    output: Path | None,
    fmt: str,
    machines_file: Path | None,
) -> None:
    """Run the Seraph HTB benchmarking harness.

    Must specify at least one of --machine, --difficulty, or --all.
    """
    if not machine and not difficulty and not run_all:
        click.echo(ctx.get_help())
        ctx.exit(1)

    try:
        specs = _load_specs(machine, difficulty, run_all, machines_file)
    except MachineLoadError as exc:
        click.echo(f"[bench] Error loading machines: {exc}", err=True)
        sys.exit(1)

    if not specs:
        click.echo("[bench] No machines matched the given filters.", err=True)
        sys.exit(1)

    click.echo(f"[bench] Running {len(specs)} machine(s) with timeout={timeout}s …")

    try:
        benchmark_report = asyncio.run(_run(specs, timeout, machines_file))
    except BenchmarkError as exc:
        click.echo(f"[bench] Benchmark failed: {exc}", err=True)
        sys.exit(1)

    # Always print summary to stdout.
    _print_summary(benchmark_report.results)

    if report or output:
        gen = ReportGenerator()
        if output:
            try:
                gen.save(benchmark_report, output, fmt=fmt)
                click.echo(f"[bench] Report saved to {output}")
            except BenchmarkError as exc:
                click.echo(f"[bench] Failed to save report: {exc}", err=True)
        else:
            click.echo(gen.to_markdown(benchmark_report))


# ── Internal helpers ──────────────────────────────────────────────────────────


def _load_specs(
    machine: str | None,
    difficulty: str | None,
    run_all: bool,
    machines_file: Path | None,
) -> list[MachineSpec]:
    """Resolve the list of machine specs from CLI options."""
    loader = MachineLoader(machines_path=machines_file)

    if machine:
        return [loader.load_by_name(machine)]
    if difficulty:
        return loader.load_by_difficulty(difficulty)  # type: ignore[arg-type]
    return loader.load_all()


async def _run(
    specs: list[MachineSpec],
    timeout: int,
    machines_file: Path | None,
) -> object:
    """Async wrapper so asyncio.run() works cleanly from Click."""
    from seraph.config import settings

    runner = BenchmarkRunner(
        api_key=getattr(settings, "anthropic_api_key", ""),
        timeout_seconds=timeout,
        machines_yaml_path=machines_file,
    )
    return await runner.run_all(specs)


def _print_summary(results: list) -> None:
    """Print a brief per-machine summary to stdout."""
    click.echo("")
    click.echo("  Machine           Outcome      Time(s)  Flags")
    click.echo("  " + "-" * 52)
    for r in results:
        flags = len(r.flags_captured)
        click.echo(
            f"  {r.machine.name:<18} {r.outcome:<12} "
            f"{r.total_time_seconds:>7.0f}  {flags}"
        )
    click.echo("  " + "-" * 52)
    solved = sum(1 for r in results if r.outcome == "solved")
    click.echo(f"  Solved: {solved}/{len(results)}")
    click.echo("")
