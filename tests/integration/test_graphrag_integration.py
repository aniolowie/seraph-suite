"""Integration tests for GraphRAG retrieval pipeline against real Neo4j."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.integration


async def _seed_neo4j(neo4j_store) -> None:
    """Seed Neo4j with minimal MITRE data for GraphRAG tests."""
    await neo4j_store.upsert_node("Tactic", "TA0002", {"id": "TA0002", "name": "Execution"})
    await neo4j_store.upsert_node(
        "Technique", "T1059", {"id": "T1059", "name": "Command Scripting"}
    )
    await neo4j_store.upsert_node(
        "Technique", "T1190", {"id": "T1190", "name": "Exploit Public-Facing App"}
    )
    await neo4j_store.upsert_node("Mitigation", "M1036", {"id": "M1036", "name": "Exec Prevention"})
    await neo4j_store.upsert_node("CVE", "CVE-2021-44228", {"id": "CVE-2021-44228"})
    await neo4j_store.upsert_relationship(
        "USES_TECHNIQUE", "Tactic", "TA0002", "Technique", "T1059"
    )
    await neo4j_store.upsert_relationship("MITIGATES", "Mitigation", "M1036", "Technique", "T1059")
    await neo4j_store.upsert_relationship(
        "EXPLOITS_CVE", "Technique", "T1190", "CVE", "CVE-2021-44228"
    )


def _make_hybrid_retriever() -> MagicMock:
    mock = AsyncMock()
    mock.retrieve = AsyncMock(
        return_value=[MagicMock(id="doc-1", score=0.9, text="Log4Shell exploit", source="nvd")]
    )
    return mock


class TestGraphRAGWithTechniqueId:
    @pytest.mark.asyncio
    async def test_technique_query_returns_graph_context(self, neo4j_store) -> None:
        from seraph.knowledge.entity_extractor import EntityExtractor
        from seraph.knowledge.graph_queries import GraphQueryLibrary
        from seraph.knowledge.graph_retriever import GraphRAGRetriever

        await _seed_neo4j(neo4j_store)
        queries = GraphQueryLibrary(neo4j_store)
        retriever = GraphRAGRetriever(
            hybrid_retriever=_make_hybrid_retriever(),
            graph_store=neo4j_store,
            query_lib=queries,
            entity_extractor=EntityExtractor(),
        )

        result = await retriever.retrieve("T1059 scripting abuse")

        assert result.has_graph_context
        assert result.entities.technique_ids == ["T1059"]

    @pytest.mark.asyncio
    async def test_technique_context_contains_technique_data(self, neo4j_store) -> None:
        from seraph.knowledge.graph_queries import GraphQueryLibrary
        from seraph.knowledge.graph_retriever import GraphRAGRetriever

        await _seed_neo4j(neo4j_store)
        queries = GraphQueryLibrary(neo4j_store)
        retriever = GraphRAGRetriever(
            hybrid_retriever=_make_hybrid_retriever(),
            graph_store=neo4j_store,
            query_lib=queries,
        )

        result = await retriever.retrieve("T1059")
        technique_ctx = next(
            (c for c in result.graph_context if c.get("technique", {}).get("id") == "T1059"),
            None,
        )
        assert technique_ctx is not None
        assert technique_ctx["technique"]["name"] == "Command Scripting"


class TestGraphRAGWithCVEId:
    @pytest.mark.asyncio
    async def test_cve_query_triggers_technique_lookup(self, neo4j_store) -> None:
        from seraph.knowledge.graph_queries import GraphQueryLibrary
        from seraph.knowledge.graph_retriever import GraphRAGRetriever

        await _seed_neo4j(neo4j_store)
        queries = GraphQueryLibrary(neo4j_store)
        retriever = GraphRAGRetriever(
            hybrid_retriever=_make_hybrid_retriever(),
            graph_store=neo4j_store,
            query_lib=queries,
        )

        result = await retriever.retrieve("CVE-2021-44228 Log4Shell")

        assert result.entities.cve_ids == ["CVE-2021-44228"]
        # vector search was called
        retriever._retriever.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_cve_falls_back_gracefully(self, neo4j_store) -> None:
        from seraph.knowledge.graph_queries import GraphQueryLibrary
        from seraph.knowledge.graph_retriever import GraphRAGRetriever

        await _seed_neo4j(neo4j_store)
        queries = GraphQueryLibrary(neo4j_store)
        retriever = GraphRAGRetriever(
            hybrid_retriever=_make_hybrid_retriever(),
            graph_store=neo4j_store,
            query_lib=queries,
        )

        # CVE not in graph — should not crash
        result = await retriever.retrieve("CVE-2099-99999")
        assert len(result.retrieved_docs) == 1


class TestGraphRAGPureVectorFallback:
    @pytest.mark.asyncio
    async def test_no_entities_returns_vector_results_only(self, neo4j_store) -> None:
        from seraph.knowledge.graph_queries import GraphQueryLibrary
        from seraph.knowledge.graph_retriever import GraphRAGRetriever

        queries = GraphQueryLibrary(neo4j_store)
        retriever = GraphRAGRetriever(
            hybrid_retriever=_make_hybrid_retriever(),
            graph_store=neo4j_store,
            query_lib=queries,
        )

        result = await retriever.retrieve("How do I enumerate SMB shares?")

        assert not result.has_graph_context
        assert len(result.retrieved_docs) == 1
