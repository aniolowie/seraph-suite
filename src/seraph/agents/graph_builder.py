"""Factory function for assembling the full Seraph LangGraph engagement graph.

Wires together all dependencies (LLM client, GraphRAG retriever, tool registry,
sub-agents, orchestrator) and returns a compiled ``StateGraph`` ready to invoke.

Usage::

    from seraph.agents.graph_builder import build_engagement_graph

    graph = build_engagement_graph(api_key="sk-ant-...")
    final_state = await graph.ainvoke(initial_state)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog
from langgraph.graph import END, StateGraph

from seraph.agents.ctf import CtfAgent
from seraph.agents.exploit import ExploitAgent
from seraph.agents.llm_client import AnthropicClient
from seraph.agents.memorist import MemoristAgent
from seraph.agents.orchestrator import OrchestratorAgent
from seraph.agents.privesc import PrivescAgent
from seraph.agents.recon import ReconAgent
from seraph.agents.state import EngagementState
from seraph.config import settings
from seraph.tools._registry import ToolRegistry
from seraph.tools.curl import CurlTool
from seraph.tools.gobuster import GobusterTool
from seraph.tools.hydra import HydraTool
from seraph.tools.linpeas import LinpeasTool
from seraph.tools.metasploit import MetasploitTool
from seraph.tools.nmap import NmapTool
from seraph.tools.sqlmap import SqlmapTool

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from seraph.knowledge.graph_builder import AttackGraphBuilder
    from seraph.knowledge.graph_retriever import GraphRAGRetriever
    from seraph.learning.feedback import FeedbackDB

log = structlog.get_logger(__name__)


def build_tool_registry(
    embedder: object | None = None,
    tools_config_path: Path | None = None,
) -> ToolRegistry:
    """Create and populate a ToolRegistry with all default tools.

    Args:
        embedder: Optional dense embedder for RAG-based selection.
        tools_config_path: Path to tools.yaml (defaults to configs/tools.yaml).

    Returns:
        Populated ``ToolRegistry``.
    """
    config_path = tools_config_path or Path("configs/tools.yaml")
    registry = ToolRegistry(
        tools_config_path=config_path if config_path.exists() else None,
        embedder=embedder,
        selection_threshold=settings.tool_selection_threshold,
    )
    registry.register_many(
        [
            NmapTool(),
            GobusterTool(),
            SqlmapTool(),
            MetasploitTool(),
            LinpeasTool(),
            CurlTool(),
            HydraTool(),
        ]
    )
    return registry


def build_engagement_graph(
    api_key: str | None = None,
    retriever: GraphRAGRetriever | None = None,
    graph_builder_obj: AttackGraphBuilder | None = None,
    embedder: object | None = None,
    max_iterations: int | None = None,
    feedback_db: FeedbackDB | None = None,
    vector_store: object | None = None,
    engagement_id: str = "",
) -> CompiledStateGraph:
    """Assemble and compile the full LangGraph engagement graph.

    Args:
        api_key: Anthropic API key (falls back to ``settings.anthropic_api_key``).
        retriever: Optional pre-constructed ``GraphRAGRetriever``.
        graph_builder_obj: Optional ``AttackGraphBuilder`` for attack graph persistence.
        embedder: Optional dense embedder for RAG tool selection.
        max_iterations: Override ``settings.agent_max_iterations``.
        feedback_db: Optional ``FeedbackDB`` for self-learning feedback logging.
        vector_store: Optional ``QdrantStore`` used by ``MemoristAgent`` for hard negative mining.
        engagement_id: Unique ID for this engagement run (used in feedback records).

    Returns:
        Compiled ``StateGraph[EngagementState]``.
    """
    resolved_key = api_key or getattr(settings, "anthropic_api_key", "")
    resolved_max = max_iterations or settings.agent_max_iterations

    llm = AnthropicClient(
        api_key=resolved_key,
        default_model=settings.sonnet_model,
        cache_enabled=settings.llm_cache_enabled,
        cache_ttl_seconds=settings.llm_cache_ttl_seconds,
    )

    registry = build_tool_registry(embedder=embedder)

    recon = ReconAgent(llm=llm, retriever=retriever, tool_registry=registry)
    exploit = ExploitAgent(llm=llm, retriever=retriever, tool_registry=registry)
    privesc = PrivescAgent(llm=llm, retriever=retriever, tool_registry=registry)
    ctf = CtfAgent(llm=llm, retriever=retriever, tool_registry=registry)
    memorist = MemoristAgent(
        llm=llm,
        retriever=retriever,
        tool_registry=registry,
        feedback_db=feedback_db,
        vector_store=vector_store,
        engagement_id=engagement_id,
    )

    orchestrator = OrchestratorAgent(
        llm=llm,
        agents={"recon": recon, "exploit": exploit, "privesc": privesc, "ctf": ctf},
        max_iterations=resolved_max,
        opus_model=settings.opus_model,
    )

    # ── LangGraph assembly ───────────────────────────────────────────────────
    graph = StateGraph(EngagementState)

    graph.add_node("orchestrator_decide", orchestrator.decide_next)
    graph.add_node("dispatch_agent", orchestrator.dispatch)
    graph.add_node("memorist", memorist.run)

    if graph_builder_obj is not None:

        async def _persist(state: EngagementState) -> EngagementState:
            await graph_builder_obj.persist_engagement_state(state)
            return state

        graph.add_node("persist_graph", _persist)
        graph.add_edge("dispatch_agent", "persist_graph")
        graph.add_edge("persist_graph", "orchestrator_decide")
    else:
        graph.add_edge("dispatch_agent", "orchestrator_decide")

    graph.add_conditional_edges(
        "orchestrator_decide",
        _routing_fn(orchestrator),
        {"continue": "dispatch_agent", "end": "memorist"},
    )
    graph.add_edge("memorist", END)

    graph.set_entry_point("orchestrator_decide")

    log.info(
        "graph_builder.assembled",
        max_iterations=resolved_max,
        persist=graph_builder_obj is not None,
        feedback_enabled=feedback_db is not None,
    )
    return graph.compile()


def _routing_fn(
    orchestrator: OrchestratorAgent,
) -> object:
    """Return a routing function that decides whether to continue or end."""

    def _route(state: EngagementState) -> Literal["continue", "end"]:
        if orchestrator.is_terminal(state):
            return "end"
        return "continue"

    return _route
