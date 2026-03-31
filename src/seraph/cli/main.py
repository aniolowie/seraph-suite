"""Main ``seraph`` CLI entrypoint.

Usage:
    seraph                      # Interactive REPL
    seraph -t 10.10.10.3        # Start engagement immediately
    seraph setup                # First-run setup wizard
    seraph ingest nvd           # Data ingestion
    seraph bench --machine Lame # HTB benchmarking
"""

from __future__ import annotations

import asyncio

import click


@click.group(invoke_without_command=True)
@click.version_option(package_name="seraph-suite")
@click.option("--target", "-t", default=None, help="Target IP/hostname — skip REPL prompt.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Stream debug logs to console.")
@click.pass_context
def cli(ctx: click.Context, target: str | None, verbose: bool) -> None:
    """Seraph — AI pentest agent suite.

    Run without arguments to enter the interactive REPL.
    Pass -t <IP> to start an engagement immediately.
    Full debug logs are always written to ~/.seraph/seraph.log.
    """
    from seraph.cli.logging_setup import configure_logging

    configure_logging(verbose=verbose)

    if ctx.invoked_subcommand is None:
        from seraph.cli.repl import SeraphREPL

        asyncio.run(SeraphREPL().run(initial_target=target))


# ── Subcommands ───────────────────────────────────────────────────────────────

from seraph.cli.bench import bench  # noqa: E402
from seraph.cli.ingest import ingest  # noqa: E402
from seraph.cli.setup import setup  # noqa: E402

cli.add_command(ingest)
cli.add_command(bench)
cli.add_command(setup)


if __name__ == "__main__":
    cli()
