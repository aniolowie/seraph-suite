"""Main `seraph` CLI entrypoint."""

from __future__ import annotations

import click


@click.group()
@click.version_option(package_name="seraph-suite")
def cli() -> None:
    """Seraph Suite — AI pentesting agent platform."""


@cli.command()
@click.option("--target", "-t", required=True, help="Target IP or hostname")
@click.option(
    "--phase",
    type=click.Choice(["recon", "enumerate", "exploit", "privesc", "post"]),
    default="recon",
    show_default=True,
)
def run(target: str, phase: str) -> None:
    """Run a pentest engagement against TARGET."""
    click.echo(f"[seraph] Starting engagement: target={target} phase={phase}")
    click.echo("[seraph] Agent orchestration not yet implemented (Phase 3).")


# Sub-commands are registered from their own modules
from seraph.cli.bench import bench  # noqa: E402
from seraph.cli.ingest import ingest  # noqa: E402

cli.add_command(ingest)
cli.add_command(bench)

if __name__ == "__main__":
    cli()
