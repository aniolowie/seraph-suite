"""CLI command: `seraph bench` — run HTB benchmarking harness."""

from __future__ import annotations

import click


@click.command(name="bench")
@click.option("--machine", "-m", default=None, help="HTB machine name")
@click.option("--difficulty", type=click.Choice(["Easy", "Medium", "Hard", "Insane"]), default=None)
@click.option(
    "--all", "run_all", is_flag=True, default=False, help="Run all machines in machines.yaml"
)
@click.option(
    "--timeout", type=int, default=3600, show_default=True, help="Timeout per machine (seconds)"
)
@click.option("--report", is_flag=True, default=False, help="Generate benchmark report")
def bench(
    machine: str | None,
    difficulty: str | None,
    run_all: bool,
    timeout: int,
    report: bool,
) -> None:
    """Run HTB benchmarking against one or more machines.

    Examples:

        seraph bench --machine Lame --timeout 3600

        seraph bench --difficulty Easy --all --report
    """
    click.echo("[bench] HTB benchmarking not yet implemented (Phase 6).")
