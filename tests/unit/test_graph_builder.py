"""Unit tests for AttackGraphBuilder."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.state import (
    EngagementState,
    Finding,
    FindingSeverity,
    GraphEdge,
    Phase,
    TargetInfo,
)
from seraph.exceptions import GraphStoreError
from seraph.knowledge.graph_builder import AttackGraphBuilder


def _make_graph_store() -> MagicMock:
    store = MagicMock()
    store.upsert_node = AsyncMock()
    store.upsert_relationship = AsyncMock()
    return store


def _make_finding(**kwargs) -> Finding:
    defaults = {
        "id": "finding-001",
        "title": "RCE via Log4Shell",
        "description": "Log4j JNDI exploit",
        "severity": FindingSeverity.CRITICAL,
        "phase": Phase.EXPLOIT,
        "cve_ids": ["CVE-2021-44228"],
        "mitre_techniques": ["T1190"],
        "evidence": "PoC worked",
    }
    return Finding(**{**defaults, **kwargs})


def _make_target(**kwargs) -> TargetInfo:
    defaults = {"ip": "10.10.10.3", "hostname": "lame", "os": "Linux", "ports": [22, 80, 445]}
    return TargetInfo(**{**defaults, **kwargs})


class TestAttackGraphBuilderPersistFinding:
    @pytest.mark.asyncio
    async def test_creates_finding_and_host_nodes(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        await builder.persist_finding(_make_finding(), _make_target())

        # Both upsert_node calls: one for Host, one for Finding
        assert store.upsert_node.call_count == 2
        labels = [c.args[0] for c in store.upsert_node.call_args_list]
        assert "Host" in labels
        assert "Finding" in labels

    @pytest.mark.asyncio
    async def test_creates_targets_edge(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        await builder.persist_finding(_make_finding(), _make_target())

        rel_types = [c.args[0] for c in store.upsert_relationship.call_args_list]
        assert "TARGETS" in rel_types

    @pytest.mark.asyncio
    async def test_creates_technique_used_edge(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        finding = _make_finding(mitre_techniques=["T1190", "T1059"])
        await builder.persist_finding(finding, _make_target())

        rel_types = [c.args[0] for c in store.upsert_relationship.call_args_list]
        assert rel_types.count("TECHNIQUE_USED") == 2

    @pytest.mark.asyncio
    async def test_creates_exploits_edge_for_each_cve(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        await builder.persist_finding(
            _make_finding(cve_ids=["CVE-2021-44228", "CVE-2022-22965"]),
            _make_target(),
        )

        rel_types = [c.args[0] for c in store.upsert_relationship.call_args_list]
        assert rel_types.count("EXPLOITS") == 2

    @pytest.mark.asyncio
    async def test_missing_technique_does_not_raise(self) -> None:
        store = _make_graph_store()
        store.upsert_relationship = AsyncMock(
            side_effect=lambda rel_type, *args, **kwargs: (
                (_ for _ in ()).throw(GraphStoreError("not found"))
                if rel_type == "TECHNIQUE_USED"
                else None
            )
        )
        builder = AttackGraphBuilder(graph_store=store)

        # Should not raise — GraphStoreError on TECHNIQUE_USED is swallowed
        await builder.persist_finding(_make_finding(), _make_target())

    @pytest.mark.asyncio
    async def test_no_cves_no_exploits_edge(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        await builder.persist_finding(_make_finding(cve_ids=[]), _make_target())

        rel_types = [c.args[0] for c in store.upsert_relationship.call_args_list]
        assert "EXPLOITS" not in rel_types

    @pytest.mark.asyncio
    async def test_no_techniques_no_technique_used_edge(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        await builder.persist_finding(_make_finding(mitre_techniques=[]), _make_target())

        rel_types = [c.args[0] for c in store.upsert_relationship.call_args_list]
        assert "TECHNIQUE_USED" not in rel_types


class TestAttackGraphBuilderPersistEdge:
    @pytest.mark.asyncio
    async def test_persist_edge_calls_upsert_relationship(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        edge = GraphEdge(source="finding-001", target="finding-002", relation="LEADS_TO")
        await builder.persist_edge(edge)

        store.upsert_relationship.assert_called_once()
        call_args = store.upsert_relationship.call_args
        assert call_args.kwargs["rel_type"] == "LEADS_TO"

    @pytest.mark.asyncio
    async def test_edge_with_technique_includes_property(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        edge = GraphEdge(
            source="f1", target="f2", relation="LEADS_TO", technique="T1059", weight=2.0
        )
        await builder.persist_edge(edge)

        props = store.upsert_relationship.call_args.kwargs.get("properties", {})
        assert props.get("technique") == "T1059"
        assert props.get("weight") == 2.0


class TestAttackGraphBuilderPersistEngagementState:
    @pytest.mark.asyncio
    async def test_persists_all_findings(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        state = EngagementState(
            target=_make_target(),
            findings=[_make_finding(id="f1"), _make_finding(id="f2")],
        )
        await builder.persist_engagement_state(state)

        # Each finding creates 2 upsert_node calls
        assert store.upsert_node.call_count == 4

    @pytest.mark.asyncio
    async def test_persists_all_edges(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        state = EngagementState(
            target=_make_target(),
            findings=[],
            attack_graph=[
                GraphEdge(source="f1", target="f2", relation="LEADS_TO"),
                GraphEdge(source="f2", target="f3", relation="LEADS_TO"),
            ],
        )
        await builder.persist_engagement_state(state)

        assert store.upsert_relationship.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_state_is_noop(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        state = EngagementState(target=_make_target())
        await builder.persist_engagement_state(state)

        store.upsert_node.assert_not_called()
        store.upsert_relationship.assert_not_called()


class TestAttackGraphBuilderCVELinks:
    @pytest.mark.asyncio
    async def test_known_cwe_creates_link(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        count = await builder.link_cves_to_techniques({"CVE-2021-44228": ["CWE-502"]})

        assert count == 1
        store.upsert_relationship.assert_called_once()
        call_args = store.upsert_relationship.call_args.args
        assert call_args[0] == "EXPLOITS_CVE"

    @pytest.mark.asyncio
    async def test_unknown_cwe_creates_no_link(self) -> None:
        store = _make_graph_store()
        builder = AttackGraphBuilder(graph_store=store)

        count = await builder.link_cves_to_techniques({"CVE-2021-99999": ["CWE-9999"]})

        assert count == 0
        store.upsert_relationship.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_error_on_link_is_swallowed(self) -> None:
        store = _make_graph_store()
        store.upsert_relationship = AsyncMock(side_effect=GraphStoreError("fail"))
        builder = AttackGraphBuilder(graph_store=store)

        count = await builder.link_cves_to_techniques({"CVE-2021-44228": ["CWE-502"]})
        assert count == 0  # error swallowed, no crash
