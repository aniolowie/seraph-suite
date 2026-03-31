"""Unit tests for BaseAgent shared infrastructure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.base_agent import BaseAgent, _error_result
from seraph.agents.state import EngagementState, TargetInfo
from seraph.exceptions import ToolTimeoutError


class _ConcreteAgent(BaseAgent):
    AGENT_NAME = "test_agent"

    async def run(self, state: EngagementState) -> EngagementState:
        return state


def _make_state() -> EngagementState:
    return EngagementState(
        target=TargetInfo(ip="10.10.10.3", hostname="lame"),
    )


def _make_agent() -> _ConcreteAgent:
    llm = MagicMock()
    return _ConcreteAgent(llm=llm)


class TestBaseAgentHelpers:
    def test_append_history_immutable(self) -> None:
        agent = _make_agent()
        state = _make_state()
        new_state = agent._append_history(state, "scan", {"target": "x"}, "done")
        assert len(state.history) == 0
        assert len(new_state.history) == 1
        assert new_state.history[0].agent == "test_agent"

    def test_add_message_immutable(self) -> None:
        agent = _make_agent()
        state = _make_state()
        new_state = agent._add_message(state, "user", "hello")
        assert len(state.messages) == 0
        assert len(new_state.messages) == 1
        assert new_state.messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_retrieve_context_with_no_retriever(self) -> None:
        agent = _make_agent()
        state = _make_state()
        result = await agent._retrieve_context(state)
        assert result is state  # unchanged when no retriever

    @pytest.mark.asyncio
    async def test_execute_tool_returns_error_result_on_timeout(self) -> None:
        mock_registry = MagicMock()
        mock_tool = AsyncMock()
        mock_tool.execute.side_effect = ToolTimeoutError("timed out")
        mock_registry.get.return_value = mock_tool

        agent = _ConcreteAgent(llm=MagicMock(), tool_registry=mock_registry)
        state = _make_state()
        result = await agent._execute_tool("nmap", {}, state.target)

        assert result.exit_code == 1
        assert "Timeout" in result.stderr

    @pytest.mark.asyncio
    async def test_select_tools_returns_empty_without_registry(self) -> None:
        agent = _make_agent()
        result = await agent._select_tools("scan ports")
        assert result == []


class TestErrorResult:
    def test_error_result_structure(self) -> None:
        r = _error_result("nmap", "connection refused")
        assert r.tool_name == "nmap"
        assert r.exit_code == 1
        assert "connection refused" in r.stderr
