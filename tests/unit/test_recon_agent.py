"""Unit tests for ReconAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.recon import ReconAgent, _parse_nmap_findings, _update_target_from_nmap
from seraph.agents.state import EngagementState, TargetInfo

_NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
<host>
  <ports>
    <port protocol="tcp" portid="22">
      <state state="open"/>
      <service name="ssh" product="OpenSSH" version="7.4"/>
    </port>
    <port protocol="tcp" portid="80">
      <state state="open"/>
      <service name="http" product="Apache" version="2.4"/>
    </port>
    <port protocol="tcp" portid="9999">
      <state state="closed"/>
      <service name="unknown"/>
    </port>
  </ports>
  <os><osmatch name="Linux 4.15"/></os>
</host>
</nmaprun>"""


def _make_state() -> EngagementState:
    return EngagementState(target=TargetInfo(ip="10.10.10.3"))


def _make_agent() -> ReconAgent:
    llm = MagicMock()
    llm.complete_with_tools = AsyncMock(return_value=("done scanning", []))
    llm.complete = AsyncMock(return_value="done")
    registry = MagicMock()
    registry.select_tools = AsyncMock(return_value=[])
    registry.to_anthropic_tools = MagicMock(return_value=[])
    return ReconAgent(llm=llm, tool_registry=registry)


class TestReconAgentRun:
    @pytest.mark.asyncio
    async def test_run_sets_current_agent(self) -> None:
        agent = _make_agent()
        state = _make_state()
        result = await agent.run(state)
        assert result.current_agent == "recon"

    @pytest.mark.asyncio
    async def test_run_appends_history(self) -> None:
        agent = _make_agent()
        state = _make_state()
        result = await agent.run(state)
        assert any(h.action == "recon_complete" for h in result.history)

    @pytest.mark.asyncio
    async def test_run_is_immutable(self) -> None:
        agent = _make_agent()
        state = _make_state()
        result = await agent.run(state)
        assert state.history == []
        assert state.messages == []
        assert result is not state


class TestNmapParsing:
    def test_parse_nmap_findings_extracts_open_ports(self) -> None:
        target = TargetInfo(ip="10.10.10.3")
        findings = _parse_nmap_findings(_NMAP_XML, target)
        assert len(findings) == 2  # only open ports
        titles = [f.title for f in findings]
        assert any("22" in t for t in titles)
        assert any("80" in t for t in titles)

    def test_parse_nmap_findings_returns_empty_on_bad_xml(self) -> None:
        target = TargetInfo(ip="10.10.10.3")
        findings = _parse_nmap_findings("not xml", target)
        assert findings == []

    def test_update_target_from_nmap_adds_ports(self) -> None:
        target = TargetInfo(ip="10.10.10.3", ports=[22])
        updated = _update_target_from_nmap(_NMAP_XML, target)
        assert 80 in updated.ports
        assert 22 in updated.ports
        assert "Linux" in updated.os
