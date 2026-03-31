"""Integration tests for the full LangGraph engagement graph.

Uses mocked LLM responses and tool outputs to simulate a complete
recon → exploit → privesc → done engagement without real network access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


def _make_mock_llm(responses: list[str]) -> MagicMock:
    """Build a mock LLM that cycles through scripted responses."""
    llm = MagicMock()
    call_count = [0]

    async def _complete(messages, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx]

    async def _complete_with_tools(messages, tools, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx], []

    llm.complete = AsyncMock(side_effect=_complete)
    llm.complete_with_tools = AsyncMock(side_effect=_complete_with_tools)
    return llm


def _make_mock_registry() -> MagicMock:
    registry = MagicMock()
    registry.select_tools = AsyncMock(return_value=[])
    registry.to_anthropic_tools = MagicMock(return_value=[])
    return registry


class TestFullEngagementGraph:
    @pytest.mark.asyncio
    async def test_graph_terminates_on_done(self) -> None:
        """Graph should terminate when orchestrator returns 'done'."""
        from seraph.agents.graph_builder import build_engagement_graph
        from seraph.agents.state import EngagementState, TargetInfo

        orchestrator_response = (
            '{"next_agent": "done", "phase": "done", "reasoning": "already done"}'
        )

        with patch("seraph.agents.graph_builder.AnthropicClient") as mock_client_cls:
            mock_llm = _make_mock_llm([orchestrator_response])
            mock_client_cls.return_value = mock_llm

            with patch("seraph.agents.graph_builder.build_tool_registry") as mock_registry_fn:
                mock_registry_fn.return_value = _make_mock_registry()

                graph = build_engagement_graph(api_key="test-key")
                initial_state = EngagementState(target=TargetInfo(ip="10.10.10.3", hostname="lame"))
                final_state = await graph.ainvoke(initial_state)

        assert final_state is not None

    @pytest.mark.asyncio
    async def test_graph_increments_iteration_on_dispatch(self) -> None:
        """Each dispatch increments the iteration counter."""
        from seraph.agents.graph_builder import build_engagement_graph
        from seraph.agents.orchestrator import OrchestratorAgent
        from seraph.agents.state import EngagementState, TargetInfo

        responses = [
            '{"next_agent": "recon", "phase": "recon", "reasoning": "start"}',
            '{"next_agent": "done", "phase": "done", "reasoning": "finished"}',
        ]

        with patch("seraph.agents.graph_builder.AnthropicClient") as mock_client_cls:
            mock_llm = _make_mock_llm(responses)
            mock_client_cls.return_value = mock_llm

            with patch("seraph.agents.graph_builder.build_tool_registry") as mock_registry_fn:
                mock_registry_fn.return_value = _make_mock_registry()

                dispatch_patch = patch.object(OrchestratorAgent, "dispatch", new_callable=AsyncMock)
                with dispatch_patch as mock_dispatch:

                    async def _dispatch_side_effect(state):
                        return state.model_copy(update={"iteration": state.iteration + 1})

                    mock_dispatch.side_effect = _dispatch_side_effect

                    graph = build_engagement_graph(api_key="test-key")
                    initial_state = EngagementState(target=TargetInfo(ip="10.10.10.3"))
                    final_state = await graph.ainvoke(initial_state)

        assert final_state["iteration"] >= 1

    @pytest.mark.asyncio
    async def test_graph_respects_max_iterations(self) -> None:
        """Graph terminates when max_iterations is reached."""
        from seraph.agents.graph_builder import build_engagement_graph
        from seraph.agents.orchestrator import OrchestratorAgent
        from seraph.agents.state import EngagementState, TargetInfo

        always_recon = '{"next_agent": "recon", "phase": "recon", "reasoning": "keep going"}'

        with patch("seraph.agents.graph_builder.AnthropicClient") as mock_client_cls:
            mock_llm = _make_mock_llm([always_recon] * 20)
            mock_client_cls.return_value = mock_llm

            with patch("seraph.agents.graph_builder.build_tool_registry") as mock_registry_fn:
                mock_registry_fn.return_value = _make_mock_registry()

                dispatch_patch = patch.object(OrchestratorAgent, "dispatch", new_callable=AsyncMock)
                with dispatch_patch as mock_dispatch:

                    async def _dispatch_bump(state):
                        return state.model_copy(update={"iteration": state.iteration + 1})

                    mock_dispatch.side_effect = _dispatch_bump

                    graph = build_engagement_graph(api_key="test-key", max_iterations=3)
                    initial_state = EngagementState(target=TargetInfo(ip="10.10.10.3"))
                    final_state = await graph.ainvoke(initial_state)

        assert final_state["iteration"] <= 3
