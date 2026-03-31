"""Privilege escalation sub-agent — root/SYSTEM access.

Runs LinPEAS enumeration, analyses output with KB context, selects the
most promising privesc vector, and captures the root flag.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from seraph.agents.base_agent import BaseAgent
from seraph.agents.state import (
    EngagementState,
    Finding,
    FindingSeverity,
    Phase,
)

log = structlog.get_logger(__name__)

_FLAG_RE = re.compile(r"[a-fA-F0-9]{32}|HTB\{[^}]+\}|flag\{[^}]+\}", re.IGNORECASE)
_JSON_BLOCK_RE = re.compile(r"\{[^{}]+\}", re.DOTALL)
_SUID_RE = re.compile(r"SUID.*?(/[^\s]+)", re.IGNORECASE)
_SUDO_RE = re.compile(r"(sudo|SUDO).*?(/[^\s]+)", re.IGNORECASE)


class PrivescAgent(BaseAgent):
    """Privilege escalation sub-agent.

    Assumes the exploit phase has obtained an initial shell.  Enumerates
    privesc vectors via linpeas, selects the best one with LLM assistance,
    and attempts escalation to root.
    """

    AGENT_NAME = "privesc"

    async def run(self, state: EngagementState) -> EngagementState:
        """Execute privilege escalation.

        1. Run linpeas to enumerate the environment.
        2. Retrieve KB context for known privesc techniques.
        3. LLM selects and executes privesc vector.
        4. Check for root flag in output.

        Args:
            state: Current engagement state (requires prior shell access).

        Returns:
            Updated state with privesc findings and root flag if captured.
        """
        state = state.model_copy(update={"current_agent": self.AGENT_NAME})
        state = await self._retrieve_context(state)

        system_prompt = self._render_prompt(
            "privesc.jinja2",
            target=state.target,
            findings=state.findings,
            kb_context=state.kb_context,
        )

        tools = await self._select_tools(
            "privilege escalation linux suid sudo cron kernel exploit",
            phase=Phase.PRIVESC,
            top_k=5,
        )

        state = self._add_message(
            state,
            "user",
            f"You have a shell on {state.target.ip}. "
            "Run linpeas to enumerate privilege escalation vectors, then exploit the best one.",
        )

        tool_call_count = 0
        new_findings: list[Finding] = []
        captured_flags = list(state.flags)
        root_obtained = False

        while tool_call_count < self._max_tool_calls:
            text, tool_calls = await self._call_llm(state, system_prompt, tools)

            if text:
                state = self._add_message(state, "assistant", text)
                flags_in_text = _FLAG_RE.findall(text)
                for flag in flags_in_text:
                    if flag not in captured_flags:
                        captured_flags.append(flag)
                        root_obtained = True
                        log.info("privesc_agent.root_flag_captured", flag=flag[:10] + "...")

            if not tool_calls:
                finding = _parse_privesc_finding(text, state)
                if finding:
                    new_findings.append(finding)
                break

            tool_results_for_llm: list[dict[str, Any]] = []
            for call in tool_calls:
                tool_call_count += 1
                result = await self._execute_tool(call["name"], call["input"], state.target)
                state = state.model_copy(update={"tool_outputs": [*state.tool_outputs, result]})

                output_text = result.stdout + result.stderr
                flags_in_output = _FLAG_RE.findall(output_text)
                for flag in flags_in_output:
                    if flag not in captured_flags:
                        captured_flags.append(flag)
                        root_obtained = True
                        log.info("privesc_agent.flag_in_output", flag=flag[:10] + "...")

                tool_results_for_llm.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": f"exit_code={result.exit_code}\n{output_text[:3000]}",
                    }
                )

            state = self._add_message(state, "user", json.dumps(tool_results_for_llm))

        new_phase = Phase.POST if root_obtained else state.phase
        state = state.model_copy(
            update={
                "findings": [*state.findings, *new_findings],
                "flags": captured_flags,
                "phase": new_phase,
            }
        )
        state = self._append_history(
            state,
            action="privesc_complete",
            input_data={"target": state.target.ip, "root": root_obtained},
            output=f"Root: {root_obtained}, Flags: {len(captured_flags)}",
        )

        log.info(
            "privesc_agent.complete",
            target=state.target.ip,
            root_obtained=root_obtained,
            total_flags=len(captured_flags),
        )
        return state


# ── Parsing helpers ───────────────────────────────────────────────────────────


def _parse_privesc_finding(llm_text: str, state: EngagementState) -> Finding | None:
    """Extract a structured privesc finding from the LLM's text response."""
    match = _JSON_BLOCK_RE.search(llm_text)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        vector = data.get("vector", "Unknown vector")
        result_str = data.get("result", "unknown")
        techniques = data.get("mitre_techniques", ["T1068"])
        root_obtained = bool(data.get("root_obtained", False))
        severity = FindingSeverity.CRITICAL if root_obtained else FindingSeverity.HIGH
        return Finding(
            id=f"privesc-{state.target.ip}-{vector[:20].replace(' ', '-')}",
            title=f"Privesc: {vector}",
            description=f"Result: {result_str}, Root: {root_obtained}",
            severity=severity,
            phase=Phase.PRIVESC,
            mitre_techniques=techniques,
        )
    except (json.JSONDecodeError, KeyError):
        return None
