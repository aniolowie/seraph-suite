"""Tool registry — loads configs/tools.yaml and manages tool instances.

Provides phase-based filtering and RAG-based top-K tool selection when the
number of available tools exceeds a configured threshold.

Usage::

    registry = ToolRegistry(tools_config_path=Path("configs/tools.yaml"))
    registry.register(NmapTool())
    recon_tools = registry.get_for_phase(Phase.RECON)
    selected = await registry.select_tools("scan for open ports on 10.0.0.1", top_k=3)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import structlog
import yaml

from seraph.agents.state import Phase
from seraph.exceptions import ToolNotFoundError
from seraph.tools._base import BaseTool

log = structlog.get_logger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ToolRegistry:
    """Central registry for all pentesting tool wrappers.

    Args:
        tools_config_path: Path to ``configs/tools.yaml``.
        embedder: Optional async dense embedder for RAG-based selection.
            If ``None``, ``select_tools`` falls back to phase filtering.
        selection_threshold: Activate RAG selection when tool count exceeds
            this value.
    """

    def __init__(
        self,
        tools_config_path: Path | None = None,
        embedder: Any | None = None,
        selection_threshold: int = 20,
    ) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._config: dict[str, Any] = {}
        self._embedder = embedder
        self._selection_threshold = selection_threshold
        self._description_embeddings: dict[str, list[float]] = {}

        if tools_config_path is not None and tools_config_path.exists():
            with tools_config_path.open() as fh:
                raw = yaml.safe_load(fh)
            self._config = raw.get("tools", {})

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """Register a concrete tool instance.

        Args:
            tool: An instantiated ``BaseTool`` subclass.
        """
        self._tools[tool.name] = tool
        log.debug("tool_registry.registered", tool=tool.name)

    def register_many(self, tools: list[BaseTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> BaseTool:
        """Return a tool by exact name.

        Raises:
            ToolNotFoundError: If no tool with that name is registered.
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' is not registered")
        return self._tools[name]

    def get_for_phase(self, phase: Phase) -> list[BaseTool]:
        """Return all tools applicable to the given engagement phase."""
        return [t for t in self._tools.values() if phase in t.phases]

    def all_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    # ── RAG-based selection ───────────────────────────────────────────────────

    async def select_tools(
        self,
        task_description: str,
        top_k: int = 5,
        phase: Phase | None = None,
    ) -> list[BaseTool]:
        """Select the most relevant tools for a task.

        When the number of candidate tools exceeds ``_selection_threshold``
        and an embedder is available, this performs cosine-similarity ranking.
        Otherwise, returns all tools filtered by phase.

        Args:
            task_description: Natural-language description of the current task.
            top_k: Maximum tools to return.
            phase: If provided, restrict candidates to this phase first.

        Returns:
            Ordered list of up to ``top_k`` tools, most relevant first.
        """
        candidates = self.get_for_phase(phase) if phase else self.all_tools()

        if len(candidates) <= self._selection_threshold or self._embedder is None:
            return candidates[:top_k]

        # Embed all tool descriptions (lazy, cached per session)
        await self._ensure_description_embeddings(candidates)

        query_vec_list: list[list[float]] = await self._embedder.embed_texts([task_description])
        query_vec = query_vec_list[0]

        scored = [
            (tool, _cosine_similarity(query_vec, self._description_embeddings[tool.name]))
            for tool in candidates
            if tool.name in self._description_embeddings
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        selected = [tool for tool, _ in scored[:top_k]]
        log.debug(
            "tool_registry.rag_selection",
            task=task_description[:60],
            selected=[t.name for t in selected],
        )
        return selected

    async def _ensure_description_embeddings(self, tools: list[BaseTool]) -> None:
        """Embed tool descriptions that haven't been embedded yet."""
        missing = [t for t in tools if t.name not in self._description_embeddings]
        if not missing or self._embedder is None:
            return
        texts = [t.description for t in missing]
        vectors: list[list[float]] = await self._embedder.embed_texts(texts)
        for tool, vec in zip(missing, vectors, strict=True):
            self._description_embeddings[tool.name] = vec

    # ── Anthropic schema export ───────────────────────────────────────────────

    def to_anthropic_tools(self, tools: list[BaseTool]) -> list[dict[str, Any]]:
        """Convert a list of tools to Anthropic tool-use schema format."""
        return [t.to_anthropic_schema() for t in tools]
