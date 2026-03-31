"""Pydantic DTOs for Neo4j attack graph nodes and relationships.

These models are graph-layer data transfer objects — they map directly to
Neo4j node labels and relationship types.  They are distinct from the agent
state models in ``seraph.agents.state`` which represent in-flight engagement
data.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Node Models ───────────────────────────────────────────────────────────────


class TacticNode(BaseModel):
    """MITRE ATT&CK Tactic (TA0001 … TA0043)."""

    id: str  # e.g. "TA0001"
    name: str
    description: str = ""
    url: str = ""
    shortname: str = ""  # e.g. "initial-access"


class TechniqueNode(BaseModel):
    """MITRE ATT&CK Technique or Sub-technique."""

    id: str  # e.g. "T1059" or "T1059.001"
    name: str
    description: str = ""
    url: str = ""
    platforms: list[str] = Field(default_factory=list)
    detection: str = ""
    is_subtechnique: bool = False
    parent_id: str = ""  # populated for sub-techniques
    tactic_ids: list[str] = Field(default_factory=list)  # e.g. ["TA0002"]


class MitigationNode(BaseModel):
    """MITRE ATT&CK Course-of-Action / Mitigation."""

    id: str  # e.g. "M1036"
    name: str
    description: str = ""
    url: str = ""


class SoftwareNode(BaseModel):
    """MITRE ATT&CK Software (malware or tool)."""

    id: str  # e.g. "S0154"
    name: str
    description: str = ""
    url: str = ""
    software_type: str = ""  # "malware" | "tool"
    platforms: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class GroupNode(BaseModel):
    """MITRE ATT&CK Intrusion Set / Threat Group."""

    id: str  # e.g. "G0007"
    name: str
    description: str = ""
    url: str = ""
    aliases: list[str] = Field(default_factory=list)


class DataSourceNode(BaseModel):
    """MITRE ATT&CK Data Source."""

    id: str  # e.g. "DS0001"
    name: str
    description: str = ""


class CVENode(BaseModel):
    """CVE node — created during NVD ingestion and cross-linked to techniques."""

    id: str  # e.g. "CVE-2021-44228"
    cvss_score: float = 0.0
    severity: str = ""
    published_date: str = ""
    cwe_ids: list[str] = Field(default_factory=list)


class FindingNode(BaseModel):
    """Engagement finding persisted to the attack graph."""

    id: str
    title: str
    severity: str
    phase: str
    cve_ids: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)
    evidence: str = ""


class HostNode(BaseModel):
    """Target host node in the attack graph."""

    ip: str
    hostname: str = ""
    os: str = ""
    ports: list[int] = Field(default_factory=list)


# ── Relationship Model ────────────────────────────────────────────────────────


class GraphRelationship(BaseModel):
    """A directed relationship between two nodes in the attack graph."""

    rel_type: str  # e.g. "USES_TECHNIQUE", "MITIGATES"
    source_label: str  # Neo4j label of the source node
    source_id: str
    target_label: str  # Neo4j label of the target node
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


# ── Parsed Bundle ─────────────────────────────────────────────────────────────


class ParsedSTIXBundle(BaseModel):
    """All extracted objects from a MITRE ATT&CK STIX bundle."""

    tactics: list[TacticNode] = Field(default_factory=list)
    techniques: list[TechniqueNode] = Field(default_factory=list)
    mitigations: list[MitigationNode] = Field(default_factory=list)
    software: list[SoftwareNode] = Field(default_factory=list)
    groups: list[GroupNode] = Field(default_factory=list)
    data_sources: list[DataSourceNode] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)
    stix_version: str = ""
