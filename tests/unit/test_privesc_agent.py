"""Unit tests for PrivescAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.privesc import PrivescAgent, _parse_privesc_finding
from seraph.agents.state import EngagementState, FindingSeverity, Phase, TargetInfo


def _make_state(**kwargs) -> EngagementState:
    defaults = {
        "target": TargetInfo(ip="10.10.10.3", os="Linux"),
        "flags": ["HTB{user_flag}"],
        "phase": Phase.PRIVESC,
    }
    return EngagementState(**{**defaults, **kwargs})


def _make_agent(llm_text: str = "no vectors found", tool_calls: list | None = None) -> PrivescAgent:
    llm = MagicMock()
    llm.complete_with_tools = AsyncMock(return_value=(llm_text, tool_calls or []))
    llm.complete = AsyncMock(return_value=llm_text)
    registry = MagicMock()
    registry.select_tools = AsyncMock(return_value=[])
    registry.to_anthropic_tools = MagicMock(return_value=[])
    return PrivescAgent(llm=llm, tool_registry=registry)


class TestPrivescAgentRun:
    @pytest.mark.asyncio
    async def test_run_sets_current_agent(self) -> None:
        agent = _make_agent()
        result = await agent.run(_make_state())
        assert result.current_agent == "privesc"

    @pytest.mark.asyncio
    async def test_run_captures_root_flag(self) -> None:
        agent = _make_agent(llm_text="Root flag: HTB{root_flag_value}")
        result = await agent.run(_make_state())
        assert "HTB{root_flag_value}" in result.flags

    @pytest.mark.asyncio
    async def test_run_transitions_to_post_on_root(self) -> None:
        agent = _make_agent(llm_text="Captured root: HTB{r00t}")
        result = await agent.run(_make_state())
        assert result.phase == Phase.POST

    @pytest.mark.asyncio
    async def test_run_appends_history(self) -> None:
        agent = _make_agent()
        result = await agent.run(_make_state())
        assert any(h.action == "privesc_complete" for h in result.history)

    @pytest.mark.asyncio
    async def test_run_preserves_existing_flags(self) -> None:
        agent = _make_agent(llm_text="no root access")
        result = await agent.run(_make_state(flags=["HTB{user_flag}"]))
        assert "HTB{user_flag}" in result.flags


class TestParsePrivescFinding:
    def test_parses_successful_privesc(self) -> None:
        state = _make_state()
        text = (
            '{"vector": "SUID vim.basic", "result": "success",'
            ' "root_obtained": true, "mitre_techniques": ["T1548"]}'
        )
        finding = _parse_privesc_finding(text, state)
        assert finding is not None
        assert finding.severity == FindingSeverity.CRITICAL
        assert "SUID vim.basic" in finding.title

    def test_parses_failed_privesc(self) -> None:
        state = _make_state()
        text = '{"vector": "kernel exploit", "result": "failed", "root_obtained": false}'
        finding = _parse_privesc_finding(text, state)
        assert finding is not None
        assert finding.severity == FindingSeverity.HIGH

    def test_returns_none_on_no_json(self) -> None:
        finding = _parse_privesc_finding("no structured output", _make_state())
        assert finding is None
