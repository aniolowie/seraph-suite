"""CLI command: `seraph ingest` — run data ingestion pipelines."""

from __future__ import annotations

import click


@click.group(name="ingest")
def ingest() -> None:
    """Ingest data into the Seraph knowledge base."""


@ingest.command(name="nvd")
@click.option("--year", type=int, default=None, help="Ingest a specific NVD year feed")
@click.option("--recent", is_flag=True, default=False, help="Ingest recent NVD feed only")
def ingest_nvd(year: int | None, recent: bool) -> None:
    """Ingest NVD/CVE data into the knowledge base."""
    click.echo("[ingest] NVD ingestion not yet implemented (Phase 1).")


@ingest.command(name="exploitdb")
@click.option("--mirror-path", type=click.Path(exists=True), default=None)
def ingest_exploitdb(mirror_path: str | None) -> None:
    """Ingest ExploitDB git mirror into the knowledge base."""
    click.echo("[ingest] ExploitDB ingestion not yet implemented (Phase 1).")


@ingest.command(name="mitre")
def ingest_mitre() -> None:
    """Ingest MITRE ATT&CK STIX data into Neo4j."""
    click.echo("[ingest] MITRE ATT&CK ingestion not yet implemented (Phase 2).")


@ingest.command(name="writeups")
@click.argument("path", type=click.Path(exists=True))
def ingest_writeups(path: str) -> None:
    """Ingest markdown writeups from PATH into the knowledge base."""
    click.echo(f"[ingest] Writeup ingestion from {path} not yet implemented (Phase 4).")
