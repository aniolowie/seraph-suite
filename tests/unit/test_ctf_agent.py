"""Unit tests for CtfAgent (7 tests)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from seraph.agents.ctf import (
    CtfAgent,
    _detect_flag_pattern,
    _extract_flags,
    _parse_flag_json,
)
from seraph.agents.state import EngagementState, Phase, TargetInfo


def _make_state(**kwargs) -> EngagementState:
    defaults = {"target": TargetInfo(ip="10.10.10.3"), "phase": Phase.EXPLOIT}
    return EngagementState(**{**defaults, **kwargs})


def _make_agent() -> CtfAgent:
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value='{"flag": "flag{test}", "technique": "T1190", "description": "found it"}'
    )
    llm.complete_with_tools = AsyncMock(return_value=('{"flag": "flag{test}"}', []))
    return CtfAgent(llm=llm, retriever=None, tool_registry=None)


def test_extract_flags_finds_standard_flag():
    """_extract_flags detects flag{...} patterns."""
    text = "Got it! flag{h3ll0_w0rld} is the answer"
    flags = _extract_flags(text)
    assert "flag{h3ll0_w0rld}" in flags


def test_extract_flags_finds_htb_flag():
    """_extract_flags detects HTB{...} flag format."""
    text = "HTB{s0m3_h4sh_h3r3}"
    flags = _extract_flags(text)
    assert "HTB{s0m3_h4sh_h3r3}" in flags


def test_extract_flags_deduplicates():
    """_extract_flags deduplicates repeated flag occurrences."""
    text = "flag{abc} ... also flag{abc} again"
    flags = _extract_flags(text)
    assert flags.count("flag{abc}") == 1


def test_detect_flag_pattern_htb():
    """_detect_flag_pattern returns HTB{...} for HTB targets."""
    state = _make_state(target=TargetInfo(ip="10.10.10.3", hostname="htb-machine"))
    assert _detect_flag_pattern(state) == "HTB{...}"


def test_parse_flag_json_extracts_flag():
    """_parse_flag_json extracts flag from structured JSON output."""
    text = 'Some text {"flag": "flag{abc}", "technique": "T1190", "description": "test"}'
    result = _parse_flag_json(text)
    assert result is not None
    assert result["flag"] == "flag{abc}"


def test_parse_flag_json_returns_none_on_no_match():
    """_parse_flag_json returns None when no JSON with flag key is present."""
    assert _parse_flag_json("no json here") is None


@pytest.mark.asyncio
async def test_run_captures_flag_from_llm_response():
    """CtfAgent.run appends flags found in LLM text to state.flags."""
    agent = _make_agent()
    # Override _call_llm to return a flag directly in the text
    agent._call_llm = AsyncMock(
        return_value=(
            '{"flag": "flag{pwned}", "technique": "T1190", "description": "SQL injection"}',
            [],
        )
    )
    agent._retrieve_context = AsyncMock(side_effect=lambda s: s)

    state = _make_state()
    result = await agent.run(state)
    assert "flag{pwned}" in result.flags
