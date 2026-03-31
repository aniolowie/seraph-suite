"""Unit tests for GraphRAGRetriever."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.state import RetrievedDoc
from seraph.knowledge.entity_extractor import EntityExtractor
from seraph.knowledge.graph_models import TechniqueNode
from seraph.knowledge.graph_retriever import GraphRAGResult, GraphRAGRetriever


def _make_doc(doc_id: str, score: float = 0.9) -> RetrievedDoc:
    return RetrievedDoc(id=doc_id, score=score, text=f"doc {doc_id}", source="nvd")


def _make_tech(tech_id: str) -> TechniqueNode:
    return TechniqueNode(id=tech_id, name=f"Technique {tech_id}")


def _make_retriever(
    query_results: list[RetrievedDoc] | None = None,
    technique_context: dict | None = None,
    cve_techniques: list[TechniqueNode] | None = None,
    tactic_techniques: list[TechniqueNode] | None = None,
) -> GraphRAGRetriever:
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=query_results or [_make_doc("d1")])

    queries = AsyncMock()
    default_ctx = {"technique": {"id": "T1059", "name": "Cmd"}}
    queries.get_technique_context = AsyncMock(
        return_value=technique_context if technique_context is not None else default_ctx
    )
    queries.find_techniques_for_cve = AsyncMock(
        return_value=cve_techniques or [_make_tech("T1190")]
    )
    queries.find_techniques_for_tactic = AsyncMock(
        return_value=tactic_techniques or [_make_tech("T1059")]
    )

    graph_store = MagicMock()
    extractor = EntityExtractor()

    return GraphRAGRetriever(
        hybrid_retriever=hybrid,
        graph_store=graph_store,
        query_lib=queries,
        entity_extractor=extractor,
    )


class TestGraphRAGRetrieverFallback:
    @pytest.mark.asyncio
    async def test_no_entities_falls_back_to_vector_search(self) -> None:
        retriever = _make_retriever()
        result = await retriever.retrieve("How do I find open ports?")

        assert isinstance(result, GraphRAGResult)
        assert not result.has_graph_context
        assert len(result.retrieved_docs) == 1
        retriever._retriever.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_entities_passes_filters_unchanged(self) -> None:
        retriever = _make_retriever()
        await retriever.retrieve("scan for services", filters={"source": "nvd"})
        call_kwargs = retriever._retriever.retrieve.call_args[1]
        assert call_kwargs.get("filters") == {"source": "nvd"}


class TestGraphRAGRetrieverWithTechniqueId:
    @pytest.mark.asyncio
    async def test_technique_id_triggers_graph_lookup(self) -> None:
        retriever = _make_retriever()
        result = await retriever.retrieve("T1059 exploitation")

        retriever._queries.get_technique_context.assert_called_once_with("T1059")
        assert result.has_graph_context

    @pytest.mark.asyncio
    async def test_technique_context_in_result(self) -> None:
        ctx = {"technique": {"id": "T1059", "name": "Cmd"}, "tactics": [], "mitigations": []}
        retriever = _make_retriever(technique_context=ctx)
        result = await retriever.retrieve("T1059")

        assert any(r.get("technique", {}).get("id") == "T1059" for r in result.graph_context)

    @pytest.mark.asyncio
    async def test_vector_search_still_called_with_entities(self) -> None:
        retriever = _make_retriever()
        result = await retriever.retrieve("T1059")

        retriever._retriever.retrieve.assert_called_once()
        assert len(result.retrieved_docs) == 1


class TestGraphRAGRetrieverWithCVEId:
    @pytest.mark.asyncio
    async def test_cve_id_triggers_technique_lookup(self) -> None:
        retriever = _make_retriever()
        result = await retriever.retrieve("CVE-2021-44228 exploitation")

        retriever._queries.find_techniques_for_cve.assert_called_once_with("CVE-2021-44228")
        assert result.entities.cve_ids == ["CVE-2021-44228"]

    @pytest.mark.asyncio
    async def test_cve_with_no_linked_techniques_still_returns_docs(self) -> None:
        retriever = _make_retriever(cve_techniques=[])
        result = await retriever.retrieve("CVE-2021-44228")

        assert len(result.retrieved_docs) == 1


class TestGraphRAGRetrieverWithTacticId:
    @pytest.mark.asyncio
    async def test_tactic_id_triggers_technique_lookup(self) -> None:
        retriever = _make_retriever()
        result = await retriever.retrieve("TA0002 execution techniques")

        retriever._queries.find_techniques_for_tactic.assert_called_once_with("TA0002")
        assert result.entities.tactic_ids == ["TA0002"]


class TestGraphRAGRetrieverErrorHandling:
    @pytest.mark.asyncio
    async def test_graph_error_does_not_fail_entire_pipeline(self) -> None:
        retriever = _make_retriever()
        retriever._queries.get_technique_context = AsyncMock(side_effect=RuntimeError("Neo4j down"))

        result = await retriever.retrieve("T1059")
        # Should still return vector results even if graph fails
        assert len(result.retrieved_docs) == 1

    @pytest.mark.asyncio
    async def test_empty_technique_context_not_added_to_graph_ctx(self) -> None:
        retriever = _make_retriever(technique_context={})
        result = await retriever.retrieve("T1059")
        # Empty dict should not be added to graph_context
        assert not result.has_graph_context


class TestGraphRAGResult:
    def test_has_graph_context_true(self) -> None:
        from seraph.knowledge.entity_extractor import ExtractedEntities

        result = GraphRAGResult(
            graph_context=[{"technique": {"id": "T1059"}}],
            retrieved_docs=[],
            entities=ExtractedEntities(),
        )
        assert result.has_graph_context

    def test_has_graph_context_false(self) -> None:
        from seraph.knowledge.entity_extractor import ExtractedEntities

        result = GraphRAGResult(
            graph_context=[],
            retrieved_docs=[_make_doc("d1")],
            entities=ExtractedEntities(),
        )
        assert not result.has_graph_context
