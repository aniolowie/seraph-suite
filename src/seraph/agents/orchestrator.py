"""Orchestrator agent — coordinates sub-agents and manages phase transitions.

The orchestrator is NOT a BaseAgent subclass: it does not call tools directly.
It reasons about the engagement state and decides which sub-agent to dispatch
next.  It enforces the iteration cap and terminates when root is captured.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog

from seraph.agents.state import EngagementState, Phase
from seraph.exceptions import LLMError, OrchestratorError

if TYPE_CHECKING:
    from seraph.agents.base_agent import BaseAgent, EventCallback
    from seraph.agents.llm_client import AnthropicClient

log = structlog.get_logger(__name__)

_JSON_RE = re.compile(r"\{[^{}]+\}", re.DOTALL)

_PHASE_MAP: dict[str, Phase] = {
    "recon": Phase.RECON,
    "enumerate": Phase.ENUMERATE,
    "exploit": Phase.EXPLOIT,
    "privesc": Phase.PRIVESC,
    "post": Phase.POST,
    "ctf": Phase.EXPLOIT,  # CTF challenges map to exploit phase
    "done": Phase.POST,  # treated as terminal
}

_DONE_SENTINEL = "done"


class OrchestratorAgent:
    """Central coordinator that decides which sub-agent to run next.

    Args:
        llm: Async Anthropic client (uses opus model for planning).
        agents: Dict mapping agent names to ``BaseAgent`` instances.
        max_iterations: Hard cap on total sub-agent invocations.
        opus_model: Model ID to use for orchestrator reasoning.
    """

    def __init__(
        self,
        llm: AnthropicClient,
        agents: dict[str, BaseAgent],
        max_iterations: int = 15,
        opus_model: str = "claude-opus-4-20250514",
        on_event: EventCallback = None,
    ) -> None:
        self._llm = llm
        self._agents = agents
        self._max_iterations = max_iterations
        self._opus_model = opus_model
        self._on_event = on_event

        from pathlib import Path

        from jinja2 import Environment, FileSystemLoader

        prompts_dir = Path(__file__).parent / "prompts"
        self._jinja = Environment(
            loader=FileSystemLoader(str(prompts_dir)),
            autoescape=False,
        )

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire an orchestrator-level event to the registered callback."""
        if self._on_event is not None:
            await self._on_event(event_type, data)

    # ── Public API ────────────────────────────────────────────────────────────

    async def decide_next(self, state: EngagementState) -> EngagementState:
        """Ask the LLM to decide the next agent and phase transition.

        Args:
            state: Current engagement state.

        Returns:
            State with ``current_agent`` and ``phase`` updated.

        Raises:
            OrchestratorError: If the LLM returns an unparseable response.
        """
        if state.iteration >= self._max_iterations:
            log.warning(
                "orchestrator.max_iterations_reached",
                iteration=state.iteration,
                max=self._max_iterations,
            )
            return state.model_copy(update={"current_agent": _DONE_SENTINEL})

        prompt = self._jinja.get_template("orchestrator.jinja2").render(
            target=state.target,
            phase=state.phase.value,
            iteration=state.iteration,
            max_iterations=self._max_iterations,
            findings=state.findings,
            plan=state.plan,
            flags=state.flags,
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            text = await self._llm.complete(
                messages,
                model=self._opus_model,
                max_tokens=512,
            )
        except LLMError as exc:
            raise OrchestratorError(f"LLM decision failed: {exc}") from exc

        decision = _parse_decision(text)
        next_agent = decision.get("next_agent", "")
        next_phase_str = decision.get("phase", "")
        reasoning = decision.get("reasoning", "")

        log.info(
            "orchestrator.decision",
            next_agent=next_agent,
            next_phase=next_phase_str,
            reasoning=reasoning,
            iteration=state.iteration,
        )

        new_phase = _PHASE_MAP.get(next_phase_str, state.phase)
        if new_phase != state.phase:
            await self._emit("phase_change", {"phase": new_phase.value})
        return state.model_copy(
            update={
                "current_agent": next_agent,
                "phase": new_phase,
            }
        )

    async def dispatch(self, state: EngagementState) -> EngagementState:
        """Dispatch to the selected sub-agent and increment the iteration counter.

        Args:
            state: State with ``current_agent`` set by ``decide_next``.

        Returns:
            Updated state after the sub-agent completes.
        """
        agent_name = state.current_agent
        if agent_name == _DONE_SENTINEL or agent_name not in self._agents:
            log.info("orchestrator.dispatch_skipped", agent=agent_name)
            return state

        agent = self._agents[agent_name]
        log.info("orchestrator.dispatching", agent=agent_name, iteration=state.iteration)
        await self._emit("agent_start", {"agent": agent_name, "phase": state.phase.value})

        state = state.model_copy(update={"iteration": state.iteration + 1})
        return await agent.run(state)

    def is_terminal(self, state: EngagementState) -> bool:
        """Return True if the engagement should terminate.

        Terminates when:
        - ``current_agent`` is "done" (orchestrator LLM decided).
        - Iteration cap is reached.
        - Both user and root flags are confirmed (2+ named-format flags).
          Named formats: ``HTB{...}``, ``flag{...}``, ``ctf{...}``.
          Bare 32-char hex from HTTP responses is NOT counted here.
        """
        if state.current_agent == _DONE_SENTINEL:
            return True
        if state.iteration >= self._max_iterations:
            return True
        confirmed = [
            f for f in state.flags
            if f.startswith("HTB{") or f.startswith("flag{") or f.startswith("ctf{")
            or (len(f) == 32 and f.isalnum())  # only standalone hex (from flag files)
        ]
        if len(confirmed) >= 2:
            log.info("orchestrator.all_flags_captured", flags=state.flags)
            return True
        return False


# ── Parsing helpers ───────────────────────────────────────────────────────────


def _parse_decision(text: str) -> dict[str, Any]:
    """Extract the JSON decision block from the LLM response."""
    match = _JSON_RE.search(text)
    if not match:
        log.warning("orchestrator.parse_failed", response=text[:200])
        return {"next_agent": "recon", "phase": "recon", "reasoning": "parse_failed"}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {"next_agent": "recon", "phase": "recon", "reasoning": "json_error"}
