"""GraphRAG retriever — fuses Neo4j graph context with Qdrant vector search.

Pipeline:
1. Extract CVE/technique/tactic IDs from the query (EntityExtractor).
2. If entities found: traverse Neo4j for related techniques/context.
3. Augment Qdrant filters with graph-derived entity IDs.
4. Run HybridRetriever (vector search).
5. Return GraphRAGResult (graph context + retrieved docs).

Falls back to pure vector search if no entities are found.

Usage::

    retriever = GraphRAGRetriever(
        hybrid_retriever=HybridRetriever(...),
        graph_store=Neo4jStore(),
        query_lib=GraphQueryLibrary(store),
        entity_extractor=EntityExtractor(),
    )
    result = await retriever.retrieve("CVE-2021-44228 exploitation")
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from seraph.agents.state import RetrievedDoc
from seraph.knowledge.entity_extractor import EntityExtractor, ExtractedEntities
from seraph.knowledge.graph_models import TechniqueNode

log = structlog.get_logger(__name__)


class GraphRAGResult:
    """Combined result from the GraphRAG retrieval pipeline.

    Args:
        graph_context: Structured data from Neo4j (technique context bundles).
        retrieved_docs: Text chunks from Qdrant hybrid search.
        entities: Entities extracted from the original query.
    """

    def __init__(
        self,
        graph_context: list[dict],
        retrieved_docs: list[RetrievedDoc],
        entities: ExtractedEntities,
    ) -> None:
        """Initialise with all pipeline outputs."""
        self.graph_context = graph_context
        self.retrieved_docs = retrieved_docs
        self.entities = entities

    @property
    def has_graph_context(self) -> bool:
        """True if graph traversal returned any results."""
        return bool(self.graph_context)


class GraphRAGRetriever:
    """Fuses Neo4j attack graph context with Qdrant hybrid vector search.

    Args:
        hybrid_retriever: ``HybridRetriever`` for vector search.
        graph_store: ``Neo4jStore`` for graph traversal.
        query_lib: ``GraphQueryLibrary`` for Cypher queries.
        entity_extractor: ``EntityExtractor`` for entity detection.
    """

    def __init__(
        self,
        hybrid_retriever: Any,
        graph_store: Any,
        query_lib: Any,
        entity_extractor: EntityExtractor | None = None,
    ) -> None:
        """Initialise the GraphRAG retriever."""
        self._retriever = hybrid_retriever
        self._graph = graph_store
        self._queries = query_lib
        self._extractor = entity_extractor or EntityExtractor()

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> GraphRAGResult:
        """Run the full GraphRAG pipeline for a query.

        Args:
            query: Free-text query from agent or user.
            top_k: Number of results after reranking.
            filters: Additional Qdrant payload filters.

        Returns:
            ``GraphRAGResult`` with graph context + retrieved docs.
        """
        entities = self._extractor.extract(query)
        log.debug(
            "graph_retriever.extracted_entities",
            cves=entities.cve_ids,
            techniques=entities.technique_ids,
            tactics=entities.tactic_ids,
        )

        if not entities.has_entities:
            # Pure vector search fallback
            docs = await self._retriever.retrieve(query, top_k=top_k, filters=filters)
            return GraphRAGResult(graph_context=[], retrieved_docs=docs, entities=entities)

        # Run graph traversal and vector embedding in parallel
        graph_context, augmented_filters = await self._build_graph_context(entities, filters)

        docs = await self._retriever.retrieve(
            query, top_k=top_k, filters=augmented_filters or filters
        )

        log.debug(
            "graph_retriever.done",
            graph_nodes=len(graph_context),
            docs=len(docs),
        )
        return GraphRAGResult(
            graph_context=graph_context,
            retrieved_docs=docs,
            entities=entities,
        )

    async def retrieve_pure_vector(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedDoc]:
        """Bypass graph traversal — pure vector search.

        Args:
            query: Free-text query.
            top_k: Number of results.
            filters: Qdrant payload filters.

        Returns:
            Retrieved docs from vector search only.
        """
        return await self._retriever.retrieve(query, top_k=top_k, filters=filters)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _build_graph_context(
        self,
        entities: ExtractedEntities,
        base_filters: dict[str, Any] | None,
    ) -> tuple[list[dict], dict[str, Any] | None]:
        """Traverse the graph and build context + augmented filters.

        Args:
            entities: Extracted entities from the query.
            base_filters: Existing Qdrant filters to augment.

        Returns:
            Tuple of (graph_context_list, augmented_qdrant_filters).
        """
        context_tasks = []

        # Fetch technique context for each technique ID
        for tid in entities.technique_ids:
            context_tasks.append(self._queries.get_technique_context(tid))

        # Fetch techniques linked to each CVE
        for cve_id in entities.cve_ids:
            context_tasks.append(self._get_cve_context(cve_id))

        # Fetch techniques in each tactic
        for tactic_id in entities.tactic_ids:
            context_tasks.append(self._get_tactic_context(tactic_id))

        if not context_tasks:
            return [], base_filters

        results = await asyncio.gather(*context_tasks, return_exceptions=True)

        graph_context: list[dict] = []
        linked_technique_ids: list[str] = list(entities.technique_ids)

        for result in results:
            if isinstance(result, Exception):
                log.warning("graph_retriever.context_error", error=str(result))
                continue
            if isinstance(result, dict) and result:
                graph_context.append(result)
                # Collect technique IDs from context for filter augmentation
                tech = result.get("technique", {})
                if tech and tech.get("id"):
                    linked_technique_ids.append(tech["id"])
            elif isinstance(result, list):
                # Results from tactic/CVE lookups — list of TechniqueNode or context dicts
                for item in result:
                    if isinstance(item, TechniqueNode):
                        linked_technique_ids.append(item.id)
                    elif isinstance(item, dict):
                        graph_context.append(item)

        # Build augmented Qdrant filter: restrict to MITRE source + linked technique IDs
        augmented: dict[str, Any] | None = None
        if linked_technique_ids:
            augmented = {**(base_filters or {}), "source": "mitre"}

        return graph_context, augmented

    async def _get_cve_context(self, cve_id: str) -> list[TechniqueNode]:
        """Return techniques linked to a CVE."""
        try:
            return await self._queries.find_techniques_for_cve(cve_id)
        except Exception as exc:
            log.warning("graph_retriever.cve_lookup_failed", cve_id=cve_id, error=str(exc))
            return []

    async def _get_tactic_context(self, tactic_id: str) -> list[TechniqueNode]:
        """Return techniques in a tactic."""
        try:
            return await self._queries.find_techniques_for_tactic(tactic_id)
        except Exception as exc:
            log.warning("graph_retriever.tactic_lookup_failed", tactic_id=tactic_id, error=str(exc))
            return []
