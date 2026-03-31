"""CTF sub-agent — solves Capture The Flag challenges.

Handles web, pwn, crypto, forensics, reversing, and misc CTF categories.
Uses curl, gobuster, and sqlmap to probe targets, extracting flags that
match common CTF flag patterns.

Adds discovered flags directly to ``EngagementState.flags``.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from seraph.agents.base_agent import BaseAgent
from seraph.agents.state import EngagementState, Finding, FindingSeverity, Phase

log = structlog.get_logger(__name__)

# Common CTF flag patterns — covers most competitions.
_FLAG_PATTERNS = [
    re.compile(r"flag\{[^}]+\}", re.IGNORECASE),
    re.compile(r"htb\{[^}]+\}", re.IGNORECASE),
    re.compile(r"ctf\{[^}]+\}", re.IGNORECASE),
    re.compile(r"picoctf\{[^}]+\}", re.IGNORECASE),
]

_JSON_RE = re.compile(r'\{[^}]*"flag"\s*:\s*"[^"]*"[^}]*\}', re.DOTALL)


class CtfAgent(BaseAgent):
    """CTF sub-agent that solves challenges by probing services for flags.

    Enumerates web endpoints, tests common injection vectors, and extracts
    flags using pattern matching on tool output and LLM responses.
    """

    AGENT_NAME = "ctf"

    async def run(self, state: EngagementState) -> EngagementState:
        """Execute CTF challenge-solving logic.

        1. Retrieve KB context relevant to CTF techniques.
        2. Render the CTF prompt.
        3. Loop: call LLM → execute tools → extract flags.
        4. Return updated state with captured flags and findings.

        Args:
            state: Current engagement state.

        Returns:
            Updated state with flags and findings appended.
        """
        state = state.model_copy(update={"current_agent": self.AGENT_NAME})
        state = await self._retrieve_context(state)

        flag_pattern = _detect_flag_pattern(state)
        system_prompt = self._render_prompt(
            "ctf.jinja2",
            target=state.target,
            phase=state.phase.value,
            kb_context=state.kb_context,
            findings=state.findings,
            flags=state.flags,
            flag_pattern=flag_pattern,
        )

        tools = await self._select_tools(
            "CTF challenge web enumeration path discovery injection",
            phase=Phase.EXPLOIT,
            top_k=5,
        )

        state = self._add_message(
            state,
            "user",
            f"Solve the CTF challenge on {state.target.ip}. "
            f"Identify the category and capture the flag.",
        )

        tool_call_count = 0
        new_flags: list[str] = []
        new_findings: list[Finding] = []

        while tool_call_count < self._max_tool_calls:
            text, tool_calls = await self._call_llm(state, system_prompt, tools)

            # Extract flags from LLM text
            flags_in_text = _extract_flags(text)
            new_flags.extend(f for f in flags_in_text if f not in state.flags + new_flags)

            if text:
                state = self._add_message(state, "assistant", text)

            if not tool_calls:
                # Try to parse structured flag response
                parsed = _parse_flag_json(text)
                if parsed:
                    flag = parsed.get("flag", "")
                    if flag and flag not in state.flags + new_flags:
                        new_flags.append(flag)
                        new_findings.append(_make_flag_finding(parsed, state))
                break

            for call in tool_calls:
                tool_call_count += 1
                result = await self._execute_tool(call["name"], call["input"], state.target)
                state = state.model_copy(update={"tool_outputs": [*state.tool_outputs, result]})

                # Scan tool output for flags
                flags_in_output = _extract_flags(result.stdout)
                new_flags.extend(f for f in flags_in_output if f not in state.flags + new_flags)

                state = self._add_message(
                    state,
                    "user",
                    json.dumps(
                        [
                            {
                                "type": "tool_result",
                                "tool_use_id": call["id"],
                                "content": f"exit_code={result.exit_code}\n{result.stdout[:3000]}",
                            }
                        ]
                    ),
                )

            if new_flags:
                log.info("ctf_agent.flags_found", flags=new_flags)
                break

        state = state.model_copy(
            update={
                "flags": [*state.flags, *new_flags],
                "findings": [*state.findings, *new_findings],
            }
        )
        state = self._append_history(
            state,
            action="ctf_solve_attempt",
            input_data={"target": state.target.ip},
            output=f"Captured {len(new_flags)} flag(s): {new_flags}",
        )

        log.info(
            "ctf_agent.complete",
            target=state.target.ip,
            new_flags=len(new_flags),
            total_flags=len(state.flags),
        )
        return state


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_flags(text: str) -> list[str]:
    """Extract all flag-pattern matches from a text string."""
    flags: list[str] = []
    for pattern in _FLAG_PATTERNS:
        flags.extend(pattern.findall(text))
    return list(dict.fromkeys(flags))  # deduplicate preserving order


def _detect_flag_pattern(state: EngagementState) -> str:
    """Infer the expected flag format from target notes or hostname."""
    notes = (state.target.notes + " " + state.target.hostname).lower()
    if "htb" in notes or "hackthebox" in notes:
        return "HTB{...}"
    if "picoctf" in notes:
        return "picoCTF{...}"
    return "flag{...}"


def _parse_flag_json(text: str) -> dict[str, Any] | None:
    """Parse a structured flag JSON block from LLM output."""
    match = _JSON_RE.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _make_flag_finding(parsed: dict[str, Any], state: EngagementState) -> Finding:
    """Build a Finding object from a parsed flag JSON dict."""
    return Finding(
        id=f"ctf-flag-{len(state.flags)}",
        title=f"Flag captured: {parsed.get('flag', 'unknown')}",
        description=parsed.get("description", "CTF flag captured."),
        severity=FindingSeverity.CRITICAL,
        phase=Phase.EXPLOIT,
        mitre_techniques=[parsed.get("technique", "T1190")],
    )
