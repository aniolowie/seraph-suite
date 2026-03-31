"""Writeup ingestion pipeline for HTB and CTF markdown writeups.

Parses local markdown files, extracts metadata via frontmatter (title,
source, difficulty, techniques), chunks the content, and upserts into
Qdrant.  Files are tracked in IngestionStateDB to avoid re-ingestion.

Expected frontmatter fields (all optional):
    title: str
    source: "htb" | "ctftime" | "ctf"
    difficulty: "easy" | "medium" | "hard"
    machine: str         # HTB machine name
    techniques: list[str]  # MITRE technique IDs
    tags: list[str]
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import structlog

from seraph.exceptions import WriteupIngestionError
from seraph.ingestion.chunker import chunk_markdown
from seraph.ingestion.models import IngestionRecord
from seraph.ingestion.state import IngestionStateDB

if False:  # TYPE_CHECKING
    from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
    from seraph.knowledge.vectorstore import QdrantStore

log = structlog.get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SOURCE_LABEL = "writeup"


class WriteupIngestor:
    """Ingests markdown writeup files from a local directory.

    Args:
        dense_embedder: Dense embedding model.
        sparse_embedder: BM25 sparse embedding model.
        vector_store: Qdrant vector store.
        state_db: Ingestion state tracker.
    """

    def __init__(
        self,
        dense_embedder: DenseEmbedder,
        sparse_embedder: SparseEmbedder,
        vector_store: QdrantStore,
        state_db: IngestionStateDB,
    ) -> None:
        self._dense = dense_embedder
        self._sparse = sparse_embedder
        self._store = vector_store
        self._state = state_db

    async def ingest(
        self,
        writeups_dir: Path | None = None,
        force: bool = False,
    ) -> int:
        """Ingest all markdown writeups in a directory.

        Args:
            writeups_dir: Directory containing .md writeup files.
                Defaults to ``./data/writeups``.
            force: Re-ingest files even if already tracked.

        Returns:
            Count of newly ingested writeups.

        Raises:
            WriteupIngestionError: On directory traversal or embedding failure.
        """
        base_dir = writeups_dir or Path("./data/writeups")
        if not base_dir.exists():
            log.info("writeup_ingestor.dir_missing", path=str(base_dir))
            return 0

        md_files = list(base_dir.rglob("*.md"))
        log.info("writeup_ingestor.start", files=len(md_files), dir=str(base_dir))

        ingested = 0
        for file_path in md_files:
            try:
                count = await self._ingest_file(file_path, force=force)
                ingested += count
            except WriteupIngestionError as exc:
                log.warning("writeup_ingestor.file_error", path=str(file_path), error=str(exc))

        log.info("writeup_ingestor.done", ingested=ingested)
        return ingested

    async def _ingest_file(self, file_path: Path, force: bool) -> int:
        """Ingest a single markdown writeup file.

        Returns the number of chunks ingested (0 if skipped).
        """
        content = file_path.read_text(encoding="utf-8", errors="replace")
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        if not force and await self._state.is_ingested(str(file_path), _SOURCE_LABEL):
            log.debug("writeup_ingestor.skip_unchanged", path=str(file_path))
            return 0

        meta = _parse_frontmatter(content)
        body = _strip_frontmatter(content)
        title = meta.get("title", file_path.stem)

        chunks = chunk_markdown(
            text=body,
            source=_SOURCE_LABEL,
            doc_id=file_hash,
            metadata={
                "title": title,
                "source": meta.get("source", "writeup"),
                "difficulty": meta.get("difficulty", ""),
                "machine": meta.get("machine", ""),
                "techniques": meta.get("techniques", []),
                "tags": meta.get("tags", []),
                "file_path": str(file_path),
            },
        )

        if not chunks:
            return 0

        # Embed
        texts = [c.text for c in chunks]
        try:
            dense_vecs = await self._dense.embed_texts(texts)
            sparse_vecs = await self._sparse.embed_texts(texts)
        except Exception as exc:
            raise WriteupIngestionError(f"Embedding failed for {file_path}: {exc}") from exc

        try:
            await self._store.upsert_chunks(chunks, dense_vecs, sparse_vecs)
        except Exception as exc:
            raise WriteupIngestionError(f"Upsert failed for {file_path}: {exc}") from exc

        record = IngestionRecord(
            source_id=str(file_path),
            source=_SOURCE_LABEL,
            chunk_count=len(chunks),
        )
        await self._state.mark_ingested(record)

        log.info(
            "writeup_ingestor.file_done",
            path=str(file_path),
            title=title,
            chunks=len(chunks),
        )
        return len(chunks)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter as a dict (best-effort, no strict YAML parse)."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    try:
        import yaml  # type: ignore[import-untyped]

        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter block from markdown content."""
    return _FRONTMATTER_RE.sub("", content, count=1)
