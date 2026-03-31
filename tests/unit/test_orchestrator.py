"""Unit tests for OrchestratorAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.orchestrator import OrchestratorAgent, _parse_decision
from seraph.agents.state import EngagementState, Phase, TargetInfo


def _make_state(**kwargs) -> EngagementState:
    defaults = {"target": TargetInfo(ip="10.10.10.3")}
    return EngagementState(**{**defaults, **kwargs})


_DEFAULT_RESPONSE = '{"next_agent": "recon", "phase": "recon", "reasoning": "start"}'


def _make_llm(response: str = _DEFAULT_RESPONSE) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


def _make_orchestrator(response: str = _DEFAULT_RESPONSE) -> OrchestratorAgent:
    return OrchestratorAgent(
        llm=_make_llm(response),
        agents={
            "recon": AsyncMock(),
            "exploit": AsyncMock(),
            "privesc": AsyncMock(),
        },
        max_iterations=10,
    )


class TestOrchestratorDecide:
    @pytest.mark.asyncio
    async def test_decide_sets_next_agent(self) -> None:
        orch = _make_orchestrator(_DEFAULT_RESPONSE)
        state = _make_state()
        new_state = await orch.decide_next(state)
        assert new_state.current_agent == "recon"

    @pytest.mark.asyncio
    async def test_decide_updates_phase(self) -> None:
        resp = '{"next_agent": "exploit", "phase": "exploit", "reasoning": "found services"}'
        orch = _make_orchestrator(resp)
        state = _make_state()
        new_state = await orch.decide_next(state)
        assert new_state.phase == Phase.EXPLOIT

    @pytest.mark.asyncio
    async def test_max_iterations_forces_done(self) -> None:
        orch = _make_orchestrator()
        state = _make_state(iteration=10)
        new_state = await orch.decide_next(state)
        assert new_state.current_agent == "done"

    @pytest.mark.asyncio
    async def test_dispatch_calls_correct_agent(self) -> None:
        recon_mock = AsyncMock()
        recon_mock.run = AsyncMock(return_value=_make_state())
        orch = OrchestratorAgent(
            llm=_make_llm(),
            agents={"recon": recon_mock, "exploit": AsyncMock(), "privesc": AsyncMock()},
            max_iterations=10,
        )
        state = _make_state(current_agent="recon", iteration=0)
        await orch.dispatch(state)
        recon_mock.run.assert_called_once()


class TestOrchestratorIsTerminal:
    def test_terminal_when_done_sentinel(self) -> None:
        orch = _make_orchestrator()
        state = _make_state(current_agent="done")
        assert orch.is_terminal(state) is True

    def test_terminal_when_max_iterations(self) -> None:
        orch = _make_orchestrator()
        state = _make_state(iteration=10)
        assert orch.is_terminal(state) is True

    def test_terminal_when_two_flags_captured(self) -> None:
        orch = _make_orchestrator()
        state = _make_state(flags=["flag1", "flag2"])
        assert orch.is_terminal(state) is True

    def test_not_terminal_with_one_flag(self) -> None:
        orch = _make_orchestrator()
        state = _make_state(flags=["flag1"], iteration=0)
        assert orch.is_terminal(state) is False


class TestParseDecision:
    def test_parses_valid_json(self) -> None:
        json_str = '{"next_agent": "exploit", "phase": "exploit", "reasoning": "ok"}'
        result = _parse_decision(f"Some text {json_str}")
        assert result["next_agent"] == "exploit"

    def test_returns_default_on_no_json(self) -> None:
        result = _parse_decision("no json here at all")
        assert result["next_agent"] == "recon"

    def test_returns_default_on_invalid_json(self) -> None:
        result = _parse_decision("{broken json")
        assert result["next_agent"] == "recon"
