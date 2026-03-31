"""MITRE ATT&CK ingestion orchestrator.

Downloads (if needed) the Enterprise ATT&CK STIX bundle, parses it with
``MITRESTIXParser``, batch-upserts nodes and relationships into Neo4j, and
dual-writes technique descriptions to Qdrant as ``DocumentChunk`` objects.

Usage::

    ingestor = MITREIngestor(graph_store=Neo4jStore(), ...)
    count = await ingestor.ingest()
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import structlog

from seraph.config import settings
from seraph.exceptions import MITREIngestionError
from seraph.ingestion.chunker import prepend_source_tag, single_chunk
from seraph.ingestion.mitre_parser import MITRESTIXParser, _node_to_dict
from seraph.ingestion.models import DocumentChunk, IngestionRecord
from seraph.ingestion.state import IngestionStateDB

log = structlog.get_logger(__name__)

# Public URL for the Enterprise ATT&CK STIX bundle
_STIX_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
)

# Node labels in topological order (tactics before techniques)
_NODE_LABEL_ORDER = [
    "Tactic",
    "Technique",
    "Mitigation",
    "Software",
    "Group",
    "DataSource",
]


class MITREIngestor:
    """Ingest MITRE ATT&CK Enterprise into Neo4j and Qdrant.

    Args:
        graph_store: ``Neo4jStore`` instance.
        dense_embedder: ``DenseEmbedder`` for technique chunk embeddings.
        sparse_embedder: ``SparseEmbedder`` for BM25 embeddings.
        vector_store: ``QdrantStore`` for technique chunk dual-write.
        state_db: ``IngestionStateDB`` for idempotency tracking.
        stix_path: Override STIX bundle path (default: ``settings.mitre_stix_path``).
    """

    def __init__(
        self,
        graph_store: Any,
        dense_embedder: Any,
        sparse_embedder: Any,
        vector_store: Any,
        state_db: IngestionStateDB,
        stix_path: Path | None = None,
    ) -> None:
        """Initialise the ingestor with all required dependencies."""
        self._graph = graph_store
        self._dense = dense_embedder
        self._sparse = sparse_embedder
        self._store = vector_store
        self._state_db = state_db
        self._stix_path = stix_path or settings.mitre_stix_path

    async def ingest(self, force: bool = False, download: bool = False) -> int:
        """Run the full MITRE ingestion pipeline.

        Steps:
        1. Download STIX bundle if missing or ``download=True``.
        2. Check idempotency — skip if already ingested (unless ``force``).
        3. Parse bundle with ``MITRESTIXParser``.
        4. Batch-upsert all nodes and relationships into Neo4j.
        5. Dual-write technique descriptions as Qdrant chunks.
        6. Record ingestion in SQLite.

        Args:
            force: Clear existing MITRE data and re-ingest.
            download: Force re-download of the STIX bundle.

        Returns:
            Total number of nodes ingested (sum across all labels).

        Raises:
            MITREIngestionError: On download, parse, or DB failure.
        """
        try:
            await self._ensure_stix_file(download)
            bundle = self._load_bundle()
            source_id = f"mitre-{bundle.get('id', 'unknown')}"

            if not force and await self._state_db.is_ingested(source_id, "mitre"):
                log.info("mitre.already_ingested", source_id=source_id)
                return 0

            if force:
                log.info("mitre.force_clear")
                for label in _NODE_LABEL_ORDER:
                    await self._graph.delete_nodes_by_label(label)
                await self._state_db.clear_source("mitre")

            parser = MITRESTIXParser()
            bundle_data = parser.parse(bundle)

            total = await self._upsert_all_nodes(bundle_data)
            await self._upsert_all_relationships(bundle_data, parser)
            await self._dual_write_techniques(bundle_data.techniques)

            await self._state_db.mark_ingested(
                IngestionRecord(source_id=source_id, source="mitre", chunk_count=total)
            )
            log.info("mitre.ingested", total_nodes=total)
            return total

        except MITREIngestionError:
            raise
        except Exception as exc:
            raise MITREIngestionError(f"MITRE ingestion failed: {exc}") from exc

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _ensure_stix_file(self, force_download: bool) -> None:
        """Download the STIX bundle if not present or forced."""
        if self._stix_path.exists() and not force_download:
            return
        self._stix_path.parent.mkdir(parents=True, exist_ok=True)
        log.info("mitre.downloading_stix", url=_STIX_URL, path=str(self._stix_path))
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                response = await client.get(_STIX_URL)
                response.raise_for_status()
            self._stix_path.write_bytes(response.content)
            log.info("mitre.stix_downloaded", size_bytes=len(response.content))
        except Exception as exc:
            raise MITREIngestionError(f"Failed to download STIX bundle: {exc}") from exc

    def _load_bundle(self) -> dict:
        """Load and JSON-parse the STIX bundle from disk."""
        import json

        try:
            return json.loads(self._stix_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MITREIngestionError(f"Failed to load STIX bundle: {exc}") from exc

    async def _upsert_all_nodes(self, bundle_data: Any) -> int:
        """Batch-upsert all node types into Neo4j."""
        total = 0
        label_map = {
            "Tactic": bundle_data.tactics,
            "Technique": bundle_data.techniques,
            "Mitigation": bundle_data.mitigations,
            "Software": bundle_data.software,
            "Group": bundle_data.groups,
            "DataSource": bundle_data.data_sources,
        }
        for label in _NODE_LABEL_ORDER:
            nodes = label_map[label]
            if not nodes:
                continue
            rows = [_node_to_dict(n) for n in nodes]
            await self._graph.upsert_nodes_batch(label, rows)
            log.info("mitre.nodes_upserted", label=label, count=len(rows))
            total += len(rows)
        return total

    async def _upsert_all_relationships(self, bundle_data: Any, parser: MITRESTIXParser) -> None:
        """Build and batch-upsert all relationships."""
        rels = list(bundle_data.relationships)
        rels.extend(parser.build_tactic_technique_rels(bundle_data.techniques))
        rels.extend(parser.build_subtechnique_rels(bundle_data.techniques))
        if rels:
            await self._graph.upsert_relationships_batch(rels)
            log.info("mitre.relationships_upserted", count=len(rels))

    async def _dual_write_techniques(self, techniques: list[Any]) -> None:
        """Write technique descriptions as Qdrant DocumentChunks.

        Each technique becomes a single chunk prefixed with its ATT&CK ID.
        Enables hybrid retrieval of technique descriptions alongside CVEs.
        """
        if not techniques:
            return
        chunks: list[DocumentChunk] = []
        for tech in techniques:
            text = tech.description or tech.name
            if not text.strip():
                continue
            tagged = prepend_source_tag(
                single_chunk(text),
                f"[{tech.id}] {tech.name}",
            )
            chunks.append(
                DocumentChunk(
                    id=f"mitre-{tech.id}",
                    text=tagged,
                    source="mitre",
                    doc_type="technique",
                    metadata={
                        "technique_id": tech.id,
                        "technique_name": tech.name,
                        "platforms": tech.platforms,
                        "tactic_ids": tech.tactic_ids,
                    },
                )
            )

        batch_size = settings.ingestion_batch_size
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            dense_vecs, sparse_vecs = await _gather(
                self._dense.embed_texts([c.text for c in batch]),
                self._sparse.embed_texts([c.text for c in batch]),
            )
            await self._store.upsert_chunks(batch, dense_vecs, sparse_vecs)
        log.info("mitre.techniques_dual_written", count=len(chunks))


async def _gather(coro1: Any, coro2: Any) -> tuple:
    """Await two coroutines in parallel."""
    import asyncio

    return await asyncio.gather(coro1, coro2)
