"""Celery tasks for async ingestion operations.

Tasks are thin wrappers that bridge Celery's synchronous task execution
to the async ingestion pipelines via ``asyncio.run()``.

Each task builds its own pipeline components to avoid sharing state
across Celery worker processes.
"""

from __future__ import annotations

import asyncio

import structlog

from seraph.exceptions import IngestionError
from seraph.worker import celery_app

log = structlog.get_logger(__name__)


def _build_nvd_ingestor() -> object:
    """Instantiate NVDIngestor with default components."""
    from seraph.ingestion.nvd import NVDIngestor
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

    return NVDIngestor(
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=IngestionStateDB(),
    )


def _build_exploitdb_ingestor() -> object:
    """Instantiate ExploitDBIngestor with default components."""
    from seraph.ingestion.exploitdb import ExploitDBIngestor
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

    return ExploitDBIngestor(
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=IngestionStateDB(),
    )


@celery_app.task(name="ingest.nvd", bind=True, max_retries=3)
def task_ingest_nvd(
    self: object,  # type: ignore[override]
    year: int | None = None,
    keyword: str | None = None,
) -> dict[str, object]:
    """Celery task: ingest NVD CVE data.

    Args:
        year: Ingest only CVEs published in this year.
        keyword: Optional NVD keyword filter.

    Returns:
        Dict with ``{"ingested": count, "source": "nvd"}``.
    """
    log.info("task.nvd.start", year=year, keyword=keyword)
    try:
        ingestor = _build_nvd_ingestor()
        count: int = asyncio.run(ingestor.ingest(year=year, keyword=keyword))  # type: ignore[attr-defined]
        log.info("task.nvd.done", count=count)
        return {"ingested": count, "source": "nvd"}
    except IngestionError as exc:
        log.error("task.nvd.failed", error=str(exc))
        raise


def _build_mitre_ingestor() -> object:
    """Instantiate MITREIngestor with default components."""
    from seraph.ingestion.mitre import MITREIngestor
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.graphstore import Neo4jStore
    from seraph.knowledge.vectorstore import QdrantStore

    return MITREIngestor(
        graph_store=Neo4jStore(),
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=IngestionStateDB(),
    )


@celery_app.task(name="ingest.exploitdb", bind=True, max_retries=3)
def task_ingest_exploitdb(
    self: object,  # type: ignore[override]
    mirror_path: str | None = None,
) -> dict[str, object]:
    """Celery task: ingest ExploitDB mirror.

    Args:
        mirror_path: Path to the local ExploitDB mirror. Uses settings default if None.

    Returns:
        Dict with ``{"ingested": count, "source": "exploitdb"}``.
    """
    from pathlib import Path

    log.info("task.exploitdb.start", mirror_path=mirror_path)
    try:
        ingestor = _build_exploitdb_ingestor()
        path = Path(mirror_path) if mirror_path else None
        count: int = asyncio.run(ingestor.ingest(mirror_path=path))  # type: ignore[attr-defined]
        log.info("task.exploitdb.done", count=count)
        return {"ingested": count, "source": "exploitdb"}
    except IngestionError as exc:
        log.error("task.exploitdb.failed", error=str(exc))
        raise


def _build_writeup_ingestor() -> object:
    """Instantiate WriteupIngestor with default components."""
    from seraph.ingestion.state import IngestionStateDB
    from seraph.ingestion.writeups import WriteupIngestor
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

    return WriteupIngestor(
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=IngestionStateDB(),
    )


def _build_ctftime_scraper() -> object:
    """Instantiate CTFTimeScraper with default components."""
    from seraph.ingestion.ctftime import CTFTimeScraper
    from seraph.ingestion.state import IngestionStateDB
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

    return CTFTimeScraper(
        dense_embedder=DenseEmbedder(),
        sparse_embedder=SparseEmbedder(),
        vector_store=QdrantStore(),
        state_db=IngestionStateDB(),
    )


@celery_app.task(name="ingest.writeups", bind=True, max_retries=3)
def task_ingest_writeups(
    self: object,  # type: ignore[override]
    writeups_dir: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Celery task: ingest local markdown writeups.

    Args:
        writeups_dir: Path to writeups directory (uses ./data/writeups if None).
        force: Re-ingest already tracked files.

    Returns:
        Dict with ``{"ingested": chunk_count, "source": "writeups"}``.
    """
    from pathlib import Path

    log.info("task.writeups.start", writeups_dir=writeups_dir)
    try:
        ingestor = _build_writeup_ingestor()
        path = Path(writeups_dir) if writeups_dir else None
        count: int = asyncio.run(ingestor.ingest(writeups_dir=path, force=force))  # type: ignore[attr-defined]
        log.info("task.writeups.done", count=count)
        return {"ingested": count, "source": "writeups"}
    except Exception as exc:
        log.error("task.writeups.failed", error=str(exc))
        raise


@celery_app.task(name="ingest.ctftime", bind=True, max_retries=3)
def task_ingest_ctftime(
    self: object,  # type: ignore[override]
    limit: int = 50,
    force: bool = False,
) -> dict[str, object]:
    """Celery task: scrape and ingest CTFTime writeups.

    Args:
        limit: Maximum writeup entries to fetch.
        force: Re-ingest already tracked entries.

    Returns:
        Dict with ``{"ingested": chunk_count, "source": "ctftime"}``.
    """
    log.info("task.ctftime.start", limit=limit)
    try:
        scraper = _build_ctftime_scraper()
        count: int = asyncio.run(scraper.ingest(limit=limit, force=force))  # type: ignore[attr-defined]
        log.info("task.ctftime.done", count=count)
        return {"ingested": count, "source": "ctftime"}
    except Exception as exc:
        log.error("task.ctftime.failed", error=str(exc))
        raise


@celery_app.task(name="ingest.mitre", bind=True, max_retries=3)
def task_ingest_mitre(
    self: object,  # type: ignore[override]
    force: bool = False,
    download: bool = False,
) -> dict[str, object]:
    """Celery task: ingest MITRE ATT&CK Enterprise into Neo4j.

    Args:
        force: Clear existing data and re-ingest.
        download: Force re-download of the STIX bundle.

    Returns:
        Dict with ``{"ingested": count, "source": "mitre"}``.
    """
    log.info("task.mitre.start", force=force, download=download)
    try:
        ingestor = _build_mitre_ingestor()
        count: int = asyncio.run(  # type: ignore[attr-defined]
            ingestor.ingest(force=force, download=download)
        )
        log.info("task.mitre.done", count=count)
        return {"ingested": count, "source": "mitre"}
    except IngestionError as exc:
        log.error("task.mitre.failed", error=str(exc))
        raise
