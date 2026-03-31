"""Abstract base class for all Seraph LangGraph sub-agents.

Provides shared infrastructure: KB context retrieval, tool selection,
LLM calls, tool execution, and immutable state history appending.

Sub-agents implement ``run()`` and define ``AGENT_NAME``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from jinja2 import Environment, FileSystemLoader

from seraph.agents.state import AgentAction, EngagementState, TargetInfo, ToolResult
from seraph.exceptions import ToolExecutionError, ToolTimeoutError

if TYPE_CHECKING:
    from seraph.agents.llm_client import AnthropicClient
    from seraph.knowledge.graph_retriever import GraphRAGRetriever
    from seraph.sandbox.executor import SandboxExecutor
    from seraph.tools._base import BaseTool
    from seraph.tools._registry import ToolRegistry

# Async callback: (event_type, data) → None
EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]] | None

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseAgent(ABC):
    """Abstract base for Seraph sub-agents.

    Args:
        name: Agent identifier (e.g. "recon").
        llm: Async Anthropic client.
        retriever: GraphRAG retriever for KB context.
        tool_registry: Registry of available tools.
        max_tool_calls: Maximum tool calls per ``run()`` invocation.
    """

    #: Override in subclasses to set the agent name used in logs/state.
    AGENT_NAME: str = "base"

    def __init__(
        self,
        llm: AnthropicClient,
        retriever: GraphRAGRetriever | None = None,
        tool_registry: ToolRegistry | None = None,
        max_tool_calls: int = 10,
        sandbox_executor: SandboxExecutor | None = None,
        container_id: str = "",
        on_event: EventCallback = None,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._registry = tool_registry
        self._max_tool_calls = max_tool_calls
        self._sandbox_executor = sandbox_executor
        self._container_id = container_id
        self._on_event = on_event
        self._jinja = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            autoescape=False,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire an event to the registered callback (no-op if none set)."""
        if self._on_event is not None:
            await self._on_event(event_type, data)

    @abstractmethod
    async def run(self, state: EngagementState) -> EngagementState:
        """Execute the agent's main logic and return updated state.

        Args:
            state: Current engagement state (treat as immutable input).

        Returns:
            New ``EngagementState`` with agent results appended.
        """

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _render_prompt(self, template_name: str, **context: Any) -> str:
        """Render a Jinja2 template from the prompts directory.

        Args:
            template_name: Template filename e.g. "recon.jinja2".
            **context: Template variables.

        Returns:
            Rendered string.
        """
        tmpl = self._jinja.get_template(template_name)
        return tmpl.render(**context)

    async def _retrieve_context(self, state: EngagementState) -> EngagementState:
        """Query the KB for context relevant to the current state.

        Returns the state with ``kb_context`` updated.
        """
        if self._retriever is None:
            return state

        query = _build_retrieval_query(state)
        try:
            result = await self._retriever.retrieve(query)
            return state.model_copy(update={"kb_context": result.retrieved_docs})
        except Exception as exc:
            log.warning("base_agent.retrieval_failed", agent=self.AGENT_NAME, error=str(exc))
            return state

    async def _select_tools(
        self,
        task_description: str,
        phase: Any | None = None,
        top_k: int = 5,
    ) -> list[BaseTool]:
        """Return relevant tools for the current task.

        Falls back to an empty list if no registry is configured.
        """
        if self._registry is None:
            return []
        return await self._registry.select_tools(task_description, top_k=top_k, phase=phase)

    async def _call_llm(
        self,
        state: EngagementState,
        system_prompt: str,
        tools: list[BaseTool] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Call the LLM with the current conversation buffer.

        Args:
            state: Current state (uses ``state.messages`` as history).
            system_prompt: System-level instructions.
            tools: Optional tools to expose via tool-use.
            model: Override the default model.
            max_tokens: Response token limit.

        Returns:
            Tuple of (text, tool_calls, raw_content_blocks).
            ``raw_content_blocks`` must be stored as the assistant message
            content so that tool_use/tool_result turns are valid for the API.

        Raises:
            LLMError: On API failure.
        """
        messages = list(state.messages) if state.messages else []

        if not tools or self._registry is None:
            text = await self._llm.complete(
                messages,
                system=system_prompt,
                model=model,
                max_tokens=max_tokens,
            )
            raw: list[dict[str, Any]] = [{"type": "text", "text": text}] if text else []
            return text, [], raw

        anthropic_tools = self._registry.to_anthropic_tools(tools)
        return await self._llm.complete_with_tools(
            messages,
            tools=anthropic_tools,
            system=system_prompt,
            model=model,
            max_tokens=max_tokens,
        )

    async def _execute_tool(
        self, tool_name: str, tool_args: dict[str, Any], target: TargetInfo
    ) -> ToolResult:
        """Execute a named tool and return its result.

        Errors are caught and returned as failed ``ToolResult`` objects so the
        LLM can reason about failures instead of crashing the agent loop.

        Args:
            tool_name: Name of the registered tool.
            tool_args: Arguments passed by the LLM.
            target: Target host info.

        Returns:
            ``ToolResult`` (may have non-zero exit_code on failure).
        """
        await self._emit("tool_start", {"name": tool_name, "args": tool_args})
        t0 = time.monotonic()

        if self._registry is None:
            result = _error_result(tool_name, "No tool registry configured")
        else:
            try:
                tool = self._registry.get(tool_name)
                # Route through sandbox when executor + container are both set.
                if self._sandbox_executor is not None and self._container_id:
                    command = tool.to_sandbox_command(tool_args, target)
                    result = await self._sandbox_executor.execute_tool(
                        self._container_id,
                        tool_name,
                        command,
                        timeout=tool.timeout,
                    )
                else:
                    result = await tool.execute(tool_args, target)
            except ToolTimeoutError as exc:
                log.warning("base_agent.tool_timeout", tool=tool_name, error=str(exc))
                result = _error_result(tool_name, f"Timeout: {exc}")
            except (ToolExecutionError, ValueError) as exc:
                log.warning("base_agent.tool_error", tool=tool_name, error=str(exc))
                result = _error_result(tool_name, str(exc))

        await self._emit("tool_end", {
            "name": tool_name,
            "exit_code": result.exit_code,
            "duration": time.monotonic() - t0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
        return result

    def _append_history(
        self,
        state: EngagementState,
        action: str,
        input_data: dict[str, Any],
        output: str,
    ) -> EngagementState:
        """Return state with a new AgentAction appended to history.

        Args:
            state: Current state.
            action: Action description.
            input_data: Input dict for the action.
            output: Output or result summary.

        Returns:
            New ``EngagementState`` with updated history.
        """
        entry = AgentAction(
            agent=self.AGENT_NAME,
            action=action,
            input=input_data,
            output=output,
        )
        return state.model_copy(update={"history": [*state.history, entry]})

    def _add_message(
        self,
        state: EngagementState,
        role: str,
        content: str | list[dict[str, Any]],
    ) -> EngagementState:
        """Append a message to the conversation buffer (immutable).

        Args:
            state: Current state.
            role: ``"user"`` or ``"assistant"``.
            content: Plain string OR a list of content blocks (required for
                proper tool_use / tool_result turns in the Anthropic API).
        """
        new_msg: dict[str, Any] = {"role": role, "content": content}
        return state.model_copy(update={"messages": [*state.messages, new_msg]})


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_retrieval_query(state: EngagementState) -> str:
    """Construct a KB retrieval query from the current engagement state."""
    parts: list[str] = [f"target {state.target.ip}"]
    if state.target.os:
        parts.append(state.target.os)
    for finding in state.findings[-3:]:
        parts.append(finding.title)
        parts.extend(finding.cve_ids[:2])
        parts.extend(finding.mitre_techniques[:2])
    return " ".join(parts)


def _error_result(tool_name: str, message: str) -> ToolResult:
    """Build a failed ToolResult with an error message."""
    return ToolResult(
        tool_name=tool_name,
        command="",
        stdout="",
        stderr=message,
        exit_code=1,
        duration_seconds=0.0,
    )
