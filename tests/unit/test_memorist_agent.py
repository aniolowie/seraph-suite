"""Unit tests for MemoristAgent (6 tests)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.memorist import MemoristAgent, _build_engagement_query, _parse_cited_ids
from seraph.agents.state import (
    EngagementState,
    Finding,
    FindingSeverity,
    Phase,
    RetrievedDoc,
    TargetInfo,
)


def _make_state(**kwargs) -> EngagementState:
    defaults = {
        "target": TargetInfo(ip="10.10.10.3"),
        "phase": Phase.POST,
        "kb_context": [
            RetrievedDoc(id="doc-001", score=0.9, text="Samba exploit CVE-2007-2447", source="nvd"),
            RetrievedDoc(id="doc-002", score=0.7, text="FTP anonymous login", source="exploitdb"),
        ],
    }
    return EngagementState(**{**defaults, **kwargs})


def _make_agent(llm_response: str = "") -> MemoristAgent:
    llm = MagicMock()
    default_response = (
        '{"cited_doc_ids": ["doc-001"], "uncited_doc_ids": ["doc-002"],'
        ' "reasoning": "doc-001 was used"}'
    )
    llm.complete = AsyncMock(return_value=llm_response or default_response)
    return MemoristAgent(llm=llm, retriever=None, tool_registry=None, engagement_id="test-eng")


def test_parse_cited_ids_extracts_from_json():
    """_parse_cited_ids returns the cited_doc_ids list from LLM JSON."""
    text = '{"cited_doc_ids": ["doc-1", "doc-2"], "uncited_doc_ids": [], "reasoning": "ok"}'
    ids = _parse_cited_ids(text)
    assert ids == ["doc-1", "doc-2"]


def test_parse_cited_ids_returns_empty_on_no_match():
    """_parse_cited_ids returns empty list when JSON is absent."""
    assert _parse_cited_ids("no json here") == []


def test_build_engagement_query_includes_target_ip():
    """_build_engagement_query includes target IP in the query string."""
    state = _make_state()
    query = _build_engagement_query(state)
    assert "10.10.10.3" in query


def test_build_engagement_query_includes_findings():
    """_build_engagement_query includes finding titles."""
    state = _make_state(
        findings=[
            Finding(
                id="f1",
                title="Samba vulnerability",
                description="test",
                severity=FindingSeverity.HIGH,
                phase=Phase.EXPLOIT,
                mitre_techniques=["T1210"],
            )
        ]
    )
    query = _build_engagement_query(state)
    assert "Samba vulnerability" in query


@pytest.mark.asyncio
async def test_run_skips_when_no_kb_context():
    """MemoristAgent.run returns state unchanged when kb_context is empty."""
    agent = _make_agent()
    state = EngagementState(target=TargetInfo(ip="10.0.0.1"), phase=Phase.POST)
    result = await agent.run(state)
    assert result.cited_doc_ids == []
    agent._llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_run_populates_cited_doc_ids():
    """MemoristAgent.run populates cited_doc_ids from LLM response."""
    agent = _make_agent(
        llm_response=(
            '{"cited_doc_ids": ["doc-001"], "uncited_doc_ids": ["doc-002"],'
            ' "reasoning": "doc-001 cited"}'
        )
    )
    state = _make_state()
    result = await agent.run(state)
    assert "doc-001" in result.cited_doc_ids
