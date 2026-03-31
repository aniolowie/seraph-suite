"""EngagementState and supporting models for the LangGraph agent graph.

The EngagementState is the single source of truth passed through every node
in the LangGraph StateGraph.  All agents read from and write back to this
typed Pydantic model — never use plain dicts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────────────


class Phase(StrEnum):
    """Current phase of the pentest engagement."""

    RECON = "recon"
    ENUMERATE = "enumerate"
    EXPLOIT = "exploit"
    PRIVESC = "privesc"
    POST = "post"
    DONE = "done"


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ── Sub-models ────────────────────────────────────────────────────────────────


class TargetInfo(BaseModel):
    """Describes the engagement target."""

    ip: str
    hostname: str = ""
    os: str = ""
    ports: list[int] = Field(default_factory=list)
    services: dict[int, str] = Field(default_factory=dict)
    notes: str = ""


class Finding(BaseModel):
    """A single discovered fact, vulnerability, or observation."""

    id: str  # e.g. "CVE-2021-44228" or "finding-001"
    title: str
    description: str
    severity: FindingSeverity = FindingSeverity.INFO
    phase: Phase
    cve_ids: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)  # e.g. ["T1210"]
    evidence: str = ""
    remediation: str = ""


class GraphEdge(BaseModel):
    """An edge in the attack graph (Neo4j-bound)."""

    source: str  # node ID
    target: str  # node ID
    relation: str  # e.g. "LEADS_TO", "EXPLOITS", "USES"
    technique: str = ""  # MITRE T-ID
    weight: float = 1.0


class RetrievedDoc(BaseModel):
    """A document chunk retrieved from the knowledge base."""

    id: str
    score: float
    text: str
    source: str  # e.g. "nvd", "exploitdb", "writeup"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Output from a pentesting tool invocation."""

    tool_name: str
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float


class PlanStep(BaseModel):
    """A single step in the agent's current plan."""

    step_id: int
    description: str
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    completed: bool = False
    result_summary: str = ""


class AgentAction(BaseModel):
    """Historical record of an agent action for the conversation buffer."""

    agent: str
    action: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    phase: Phase = Phase.RECON


# ── Main State ────────────────────────────────────────────────────────────────


class EngagementState(BaseModel):
    """Full engagement state passed through the LangGraph StateGraph.

    Every agent reads from and returns an updated copy of this model.
    State is immutable by convention — always produce a new instance
    via `state.model_copy(update={...})`.
    """

    target: TargetInfo
    phase: Phase = Phase.RECON
    findings: list[Finding] = Field(default_factory=list)
    attack_graph: list[GraphEdge] = Field(default_factory=list)
    kb_context: list[RetrievedDoc] = Field(default_factory=list)
    tool_outputs: list[ToolResult] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    history: list[AgentAction] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    error: str = ""  # Last error message, if any
    # ── Self-learning fields ──────────────────────────────────────────────────
    cited_doc_ids: list[str] = Field(
        default_factory=list,
        description="KB document IDs cited by the LLM during this engagement.",
    )
    # ── Orchestration fields ──────────────────────────────────────────────────
    messages: list[dict[str, str]] = Field(
        default_factory=list,
        description="LLM conversation buffer (role/content pairs).",
    )
    current_agent: str = ""  # Name of the agent currently executing
    iteration: int = 0  # Loop counter; enforces max_iterations guard
