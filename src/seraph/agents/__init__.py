"""Agent definitions for Seraph Suite."""

from __future__ import annotations

from seraph.agents.ctf import CtfAgent
from seraph.agents.exploit import ExploitAgent
from seraph.agents.graph_builder import build_engagement_graph
from seraph.agents.llm_client import AnthropicClient, BaseLLMClient, LocalModelClient
from seraph.agents.memorist import MemoristAgent
from seraph.agents.orchestrator import OrchestratorAgent
from seraph.agents.privesc import PrivescAgent
from seraph.agents.recon import ReconAgent
from seraph.agents.state import EngagementState, Phase

__all__ = [
    "AnthropicClient",
    "BaseLLMClient",
    "CtfAgent",
    "EngagementState",
    "ExploitAgent",
    "LocalModelClient",
    "MemoristAgent",
    "OrchestratorAgent",
    "Phase",
    "PrivescAgent",
    "ReconAgent",
    "build_engagement_graph",
]
