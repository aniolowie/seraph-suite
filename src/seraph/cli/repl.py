"""SeraphREPL — interactive pentest agent loop.

Entry point for the ``seraph`` CLI when invoked without a subcommand.
Drives the OrchestratorAgent and renders streaming events via Rich.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from seraph.agents.ctf import CtfAgent
from seraph.agents.exploit import ExploitAgent
from seraph.agents.llm_client import AnthropicClient, BaseLLMClient, LocalModelClient
from seraph.agents.memorist import MemoristAgent
from seraph.agents.orchestrator import OrchestratorAgent
from seraph.agents.privesc import PrivescAgent
from seraph.agents.recon import ReconAgent
from seraph.agents.state import EngagementState, Phase, TargetInfo
from seraph.cli.renderer import (
    console,
    prompt_input,
    render_agent_start,
    render_banner,
    render_error,
    render_finding,
    render_findings_table,
    render_help,
    render_info,
    render_llm_text,
    render_output_list,
    render_phase,
    render_status,
    render_success,
    render_tool_end,
    render_tool_output,
    render_tool_start,
    render_warning,
)
from seraph.config import settings
from seraph.exceptions import SeraphError
from seraph.tools import (
    CurlTool,
    GobusterTool,
    HydraTool,
    LinpeasTool,
    MetasploitTool,
    NmapTool,
    SqlmapTool,
    ToolRegistry,
)

log = structlog.get_logger(__name__)

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_HOST_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$")


def _build_llm_client() -> BaseLLMClient:
    """Instantiate the configured LLM client.

    Returns a ``LocalModelClient`` when ``LOCAL_MODEL_ENABLED=true`` is set,
    otherwise an ``AnthropicClient``.
    """
    if settings.local_model_enabled:
        render_info(
            f"Using local model [bold]{settings.local_model_name}[/bold]"
            f" at {settings.local_model_url}"
        )
        return LocalModelClient(
            base_url=settings.local_model_url,
            model_name=settings.local_model_name,
        )
    return AnthropicClient(api_key=settings.anthropic_api_key)


class SeraphREPL:
    """Interactive REPL that wraps the Seraph orchestrator.

    Renders streaming agent events via Rich and accepts freeform
    instructions between agent runs.
    """

    def __init__(self) -> None:
        self._state: EngagementState | None = None
        self._orchestrator: OrchestratorAgent | None = None
        self._llm: BaseLLMClient = _build_llm_client()

    async def run(self, initial_target: str | None = None) -> None:
        """Start the interactive loop.

        Args:
            initial_target: If provided, start an engagement immediately
                            instead of waiting for user input.
        """
        render_banner()

        if initial_target:
            await self._start_engagement(initial_target)

        while True:
            try:
                raw = prompt_input().strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye.[/dim]")
                break

            if not raw:
                continue

            cmd = raw.lower()

            if cmd in ("quit", "exit", "q"):
                console.print("[dim]Goodbye.[/dim]")
                break
            elif cmd in ("help", "/help"):
                render_help()
            elif cmd == "findings":
                if self._state:
                    render_findings_table([f.model_dump() for f in self._state.findings])
                else:
                    render_info("No active engagement.")
            elif cmd == "outputs":
                render_output_list()
            elif cmd == "output" or cmd.startswith("output "):
                parts = raw.split()
                idx = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                render_tool_output(idx)
            elif cmd == "status":
                if self._state:
                    render_status(
                        self._state.target.ip,
                        self._state.phase.value,
                        len(self._state.findings),
                        len(self._state.flags),
                        self._state.iteration,
                    )
                else:
                    render_info("No active engagement.")
            elif cmd == "clear":
                self._state = None
                self._orchestrator = None
                render_info("Engagement cleared.")
            elif cmd.startswith("/local"):
                self._switch_to_local(raw)
            elif cmd == "/anthropic":
                self._switch_to_anthropic()
            elif _looks_like_target(raw):
                await self._start_engagement(raw)
            elif self._state is not None:
                await self._handle_instruction(raw)
            else:
                render_info("No active engagement. Enter a target IP or hostname to start.")

    # ── Private ───────────────────────────────────────────────────────────────

    def _switch_to_local(self, raw: str) -> None:
        """Switch to a local Ollama model.

        ``/local`` uses the model configured in settings.
        ``/local <model>`` overrides with the given model tag.
        """
        parts = raw.strip().split(None, 1)
        model_name = parts[1].strip() if len(parts) > 1 else settings.local_model_name
        self._llm = LocalModelClient(
            base_url=settings.local_model_url,
            model_name=model_name,
        )
        self._orchestrator = None  # rebuild on next engagement
        render_success(
            f"Switched to local model [bold]{model_name}[/bold] at {settings.local_model_url}"
        )

    def _switch_to_anthropic(self) -> None:
        """Switch back to the Anthropic cloud API."""
        if not settings.anthropic_api_key:
            render_error("ANTHROPIC_API_KEY is not configured. Set it in .env first.")
            return
        self._llm = AnthropicClient(api_key=settings.anthropic_api_key)
        self._orchestrator = None  # rebuild on next engagement
        render_success(f"Switched to Anthropic ({settings.sonnet_model})")

    async def _start_engagement(self, target: str) -> None:
        """Initialise state and run the engagement loop."""
        render_info(f"Starting engagement against [bold]{target}[/bold]")
        self._state = EngagementState(target=TargetInfo(ip=target), phase=Phase.RECON)
        self._orchestrator = _build_orchestrator(self._llm, self._on_event)
        await self._engage()

    async def _handle_instruction(self, text: str) -> None:
        """Inject a freeform instruction and continue the loop."""
        if self._state is None or self._orchestrator is None:
            return
        self._state = self._state.model_copy(
            update={"messages": [*self._state.messages, {"role": "user", "content": text}]}
        )
        # Reset terminal flag so the loop continues
        self._state = self._state.model_copy(update={"current_agent": ""})
        await self._engage()

    async def _engage(self) -> None:
        """Drive the orchestrator until terminal or interrupted."""
        assert self._state is not None
        assert self._orchestrator is not None

        try:
            while not self._orchestrator.is_terminal(self._state):
                findings_before = len(self._state.findings)

                self._state = await self._orchestrator.decide_next(self._state)
                self._state = await self._orchestrator.dispatch(self._state)

                # Render any new findings produced during this agent run
                for f in self._state.findings[findings_before:]:
                    render_finding(f.title, f.description, f.severity.value)

        except KeyboardInterrupt:
            render_warning("Paused. Enter an instruction or new target to continue.")
        except SeraphError as exc:
            render_error(str(exc))
            log.error("repl.seraph_error", error=str(exc))

        if self._state and self._state.flags:
            render_success(f"Flags: {', '.join(self._state.flags)}")

    async def _on_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Handle streaming events from the orchestrator and agents."""
        if event_type == "tool_start":
            render_tool_start(data.get("name", ""), data.get("args", {}))
        elif event_type == "tool_end":
            render_tool_end(
                data.get("name", ""),
                data.get("exit_code", 0),
                data.get("duration", 0.0),
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
            )
        elif event_type == "phase_change":
            render_phase(data.get("phase", ""))
        elif event_type == "agent_start":
            render_agent_start(data.get("agent", ""), data.get("phase", ""))
        elif event_type == "llm_response":
            render_llm_text(data.get("text", ""))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_orchestrator(llm: BaseLLMClient, on_event: Any) -> OrchestratorAgent:
    """Construct the orchestrator with all sub-agents and tools registered."""
    registry = ToolRegistry()
    registry.register_many([
        NmapTool(),
        CurlTool(),
        GobusterTool(),
        SqlmapTool(),
        HydraTool(),
        MetasploitTool(),
        LinpeasTool(),
    ])

    agents = {
        "recon": ReconAgent(llm=llm, tool_registry=registry, max_tool_calls=4, on_event=on_event),
        "exploit": ExploitAgent(llm=llm, tool_registry=registry, on_event=on_event),
        "privesc": PrivescAgent(llm=llm, tool_registry=registry, on_event=on_event),
        "ctf": CtfAgent(llm=llm, tool_registry=registry, on_event=on_event),
        "memorist": MemoristAgent(llm=llm, tool_registry=registry, on_event=on_event),
    }
    return OrchestratorAgent(
        llm=llm,
        agents=agents,  # type: ignore[arg-type]
        max_iterations=settings.agent_max_iterations,
        on_event=on_event,
    )


def _looks_like_target(text: str) -> bool:
    """Return True if text looks like an IP or hostname."""
    return bool(_IP_RE.match(text) or _HOST_RE.match(text))
