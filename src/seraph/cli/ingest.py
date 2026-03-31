"""CLI command: `seraph ingest` — run data ingestion pipelines."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click


@click.group(name="ingest")
def ingest() -> None:
    """Ingest data into the Seraph knowledge base."""


@ingest.command(name="nvd")
@click.option("--year", type=int, default=None, help="Ingest CVEs published in this year")
@click.option("--keyword", default=None, help="NVD keyword filter")
@click.option(
    "--force", is_flag=True, default=False, help="Clear existing NVD records and re-ingest"
)
@click.option("--batch-size", type=int, default=None, help="Override ingestion batch size")
@click.option(
    "--async-mode", "async_mode", is_flag=True, default=False, help="Dispatch as Celery task"
)
def ingest_nvd(
    year: int | None,
    keyword: str | None,
    force: bool,
    batch_size: int | None,
    async_mode: bool,
) -> None:
    """Ingest NVD/CVE data into the knowledge base."""
    if batch_size is not None:
        from seraph.config import settings

        object.__setattr__(settings, "ingestion_batch_size", batch_size)  # override for this run

    if async_mode:
        from seraph.ingestion.tasks import task_ingest_nvd

        result = task_ingest_nvd.delay(year=year, keyword=keyword)
        click.echo(f"[nvd] Dispatched task: {result.id}")
        return

    from seraph.ingestion.nvd import NVDIngestor
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

    state_db = IngestionStateDB()
    if force:
        click.echo("[nvd] --force: clearing existing NVD records...")
        asyncio.run(state_db.clear_source("nvd"))

    ingestor = NVDIngestor(
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=state_db,
    )
    click.echo(f"[nvd] Starting ingestion (year={year}, keyword={keyword})...")
    count = asyncio.run(ingestor.ingest(year=year, keyword=keyword))
    click.echo(f"[nvd] Done. Ingested {count} CVEs.")


@ingest.command(name="exploitdb")
@click.option("--mirror-path", type=click.Path(), default=None, help="Path to ExploitDB mirror")
@click.option("--force", is_flag=True, default=False, help="Clear existing records and re-ingest")
@click.option("--batch-size", type=int, default=None, help="Override ingestion batch size")
@click.option(
    "--async-mode", "async_mode", is_flag=True, default=False, help="Dispatch as Celery task"
)
def ingest_exploitdb(
    mirror_path: str | None,
    force: bool,
    batch_size: int | None,
    async_mode: bool,
) -> None:
    """Ingest ExploitDB git mirror into the knowledge base.

    Clone the mirror first if not already done:

        git clone https://gitlab.com/exploit-database/exploitdb ./data/exploitdb
    """
    from seraph.config import settings

    resolved_path = Path(mirror_path) if mirror_path else settings.exploitdb_mirror_path
    if not resolved_path.exists():
        click.echo(
            f"[exploitdb] Mirror not found at {resolved_path}.\n"
            f"Clone it first: git clone https://gitlab.com/exploit-database/exploitdb"
            f" {resolved_path}",
            err=True,
        )
        raise SystemExit(1)

    if batch_size is not None:
        object.__setattr__(settings, "ingestion_batch_size", batch_size)

    if async_mode:
        from seraph.ingestion.tasks import task_ingest_exploitdb

        result = task_ingest_exploitdb.delay(mirror_path=str(resolved_path))
        click.echo(f"[exploitdb] Dispatched task: {result.id}")
        return

    from seraph.ingestion.exploitdb import ExploitDBIngestor
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

    state_db = IngestionStateDB()
    if force:
        click.echo("[exploitdb] --force: clearing existing records...")
        asyncio.run(state_db.clear_source("exploitdb"))

    ingestor = ExploitDBIngestor(
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=state_db,
    )
    click.echo(f"[exploitdb] Starting ingestion from {resolved_path}...")
    count = asyncio.run(ingestor.ingest(mirror_path=resolved_path))
    click.echo(f"[exploitdb] Done. Ingested {count} exploits.")


@ingest.command(name="mitre")
@click.option(
    "--stix-path", type=click.Path(), default=None, help="Override MITRE STIX bundle path"
)
@click.option(
    "--force", is_flag=True, default=False, help="Clear existing MITRE data and re-ingest"
)
@click.option("--download", is_flag=True, default=False, help="Force re-download STIX bundle")
@click.option(
    "--async-mode", "async_mode", is_flag=True, default=False, help="Dispatch as Celery task"
)
def ingest_mitre(
    stix_path: str | None,
    force: bool,
    download: bool,
    async_mode: bool,
) -> None:
    """Ingest MITRE ATT&CK Enterprise STIX bundle into Neo4j and Qdrant."""
    from pathlib import Path

    if async_mode:
        from seraph.ingestion.tasks import task_ingest_mitre

        result = task_ingest_mitre.delay(force=force, download=download)
        click.echo(f"[mitre] Dispatched task: {result.id}")
        return

    from seraph.ingestion.mitre import MITREIngestor
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.graphstore import Neo4jStore
    from seraph.knowledge.vectorstore import QdrantStore

    stix = Path(stix_path) if stix_path else None
    ingestor = MITREIngestor(
        graph_store=Neo4jStore(),
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=IngestionStateDB(),
        stix_path=stix,
    )
    click.echo("[mitre] Starting MITRE ATT&CK ingestion...")
    count = asyncio.run(ingestor.ingest(force=force, download=download))
    click.echo(f"[mitre] Done. Ingested {count} nodes.")


@ingest.command(name="writeups")
@click.argument("path", type=click.Path(exists=True))
def ingest_writeups(path: str) -> None:
    """Ingest markdown writeups from PATH into the knowledge base (Phase 4)."""
    click.echo(f"[writeups] Writeup ingestion from {path} not yet implemented (Phase 4).")


@ingest.command(name="stats")
@click.option("--source", default=None, help="Filter stats by source (nvd, exploitdb, ...)")
def ingest_stats(source: str | None) -> None:
    """Show ingestion statistics from the state database."""
    from seraph.ingestion.state import IngestionStateDB

    state_db = IngestionStateDB()
    sources = [source] if source else ["nvd", "exploitdb"]
    for src in sources:
        stats = asyncio.run(state_db.get_stats(src))
        if stats:
            click.echo(f"[{src}] " + " | ".join(f"{k}: {v}" for k, v in sorted(stats.items())))
        else:
            click.echo(f"[{src}] No records.")
