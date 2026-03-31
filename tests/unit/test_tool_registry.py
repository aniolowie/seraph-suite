"""Unit tests for ToolRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.exceptions import ToolNotFoundError
from seraph.tools._base import BaseTool
from seraph.tools._registry import ToolRegistry


class _FakeTool(BaseTool):
    name = "fake_tool"
    description = "A fake tool for testing"
    phases = [Phase.RECON]
    timeout = 30

    async def execute(self, args: dict, target: TargetInfo) -> ToolResult:
        return self._build_result("fake", "output", "", 0, 0.1)


class _ExploitTool(BaseTool):
    name = "exploit_tool"
    description = "An exploit tool"
    phases = [Phase.EXPLOIT]
    timeout = 60

    async def execute(self, args: dict, target: TargetInfo) -> ToolResult:
        return self._build_result("exploit", "output", "", 0, 0.1)


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = _FakeTool()
        registry.register(tool)
        assert registry.get("fake_tool") is tool

    def test_get_unknown_raises_not_found(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            registry.get("nonexistent")

    def test_get_for_phase_filters_correctly(self) -> None:
        registry = ToolRegistry()
        registry.register(_FakeTool())
        registry.register(_ExploitTool())

        recon_tools = registry.get_for_phase(Phase.RECON)
        exploit_tools = registry.get_for_phase(Phase.EXPLOIT)

        assert len(recon_tools) == 1
        assert recon_tools[0].name == "fake_tool"
        assert len(exploit_tools) == 1
        assert exploit_tools[0].name == "exploit_tool"

    @pytest.mark.asyncio
    async def test_select_tools_returns_top_k_below_threshold(self) -> None:
        registry = ToolRegistry(selection_threshold=20)
        registry.register(_FakeTool())
        registry.register(_ExploitTool())

        # Below threshold → returns all for phase, capped at top_k
        selected = await registry.select_tools("scan network", top_k=1, phase=Phase.RECON)
        assert len(selected) == 1

    @pytest.mark.asyncio
    async def test_select_tools_rag_when_above_threshold(self) -> None:
        embedder = AsyncMock()
        embedder.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])

        registry = ToolRegistry(embedder=embedder, selection_threshold=1)
        tool = _FakeTool()
        registry.register(tool)

        selected = await registry.select_tools("scan ports", top_k=5)
        assert isinstance(selected, list)

    def test_to_anthropic_tools_format(self) -> None:
        registry = ToolRegistry()
        tool = _FakeTool()
        registry.register(tool)

        schemas = registry.to_anthropic_tools([tool])
        assert len(schemas) == 1
        assert schemas[0]["name"] == "fake_tool"
        assert "description" in schemas[0]
        assert "input_schema" in schemas[0]
