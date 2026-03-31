"""Attack graph builder — persists engagement findings to Neo4j.

Called by agents during and after an engagement to record what was
discovered, exploited, and how nodes in the attack graph relate.

Usage::

    builder = AttackGraphBuilder(graph_store=Neo4jStore())
    await builder.persist_finding(finding, target)
    await builder.persist_edge(edge)
"""

from __future__ import annotations

import structlog

from seraph.agents.state import EngagementState, Finding, GraphEdge, TargetInfo
from seraph.exceptions import GraphStoreError
from seraph.knowledge.graph_models import FindingNode, HostNode

log = structlog.get_logger(__name__)


class AttackGraphBuilder:
    """Persists engagement state into the Neo4j attack graph.

    Creates Finding nodes, Host nodes, and edges that connect them to
    known MITRE techniques and CVEs.

    Args:
        graph_store: ``Neo4jStore`` instance for all writes.
    """

    def __init__(self, graph_store: object) -> None:
        """Initialise with a Neo4jStore."""
        self._graph = graph_store

    async def persist_finding(self, finding: Finding, target: TargetInfo) -> None:
        """Persist a single Finding and its relationships to Neo4j.

        Creates:
        - A ``Finding`` node from the finding data.
        - A ``Host`` node from the target info (idempotent MERGE).
        - A ``TARGETS`` edge from Finding → Host.
        - A ``TECHNIQUE_USED`` edge for each MITRE technique in the finding.
        - An ``EXPLOITS`` edge for each CVE ID in the finding.

        Args:
            finding: The ``Finding`` from the engagement state.
            target: The ``TargetInfo`` describing the target host.

        Raises:
            GraphStoreError: On Neo4j write failure.
        """
        host_node = HostNode(
            ip=target.ip,
            hostname=target.hostname,
            os=target.os,
            ports=target.ports,
        )
        finding_node = FindingNode(
            id=finding.id,
            title=finding.title,
            severity=finding.severity.value,
            phase=finding.phase.value,
            cve_ids=finding.cve_ids,
            mitre_techniques=finding.mitre_techniques,
            evidence=finding.evidence,
        )

        # Upsert host and finding nodes
        await self._graph.upsert_node("Host", host_node.ip, host_node.model_dump())
        await self._graph.upsert_node("Finding", finding_node.id, finding_node.model_dump())

        # Finding → Host
        await self._graph.upsert_relationship("TARGETS", "Finding", finding.id, "Host", target.ip)

        # Finding → Technique (for each MITRE technique)
        for tech_id in finding.mitre_techniques:
            try:
                await self._graph.upsert_relationship(
                    "TECHNIQUE_USED", "Finding", finding.id, "Technique", tech_id
                )
            except GraphStoreError:
                # Technique node may not exist if MITRE not yet ingested — skip
                log.warning(
                    "graph_builder.technique_not_found",
                    finding_id=finding.id,
                    technique_id=tech_id,
                )

        # Finding → CVE (for each CVE)
        for cve_id in finding.cve_ids:
            try:
                await self._graph.upsert_relationship(
                    "EXPLOITS", "Finding", finding.id, "CVE", cve_id
                )
            except GraphStoreError:
                log.warning(
                    "graph_builder.cve_not_found",
                    finding_id=finding.id,
                    cve_id=cve_id,
                )

        log.info(
            "graph_builder.finding_persisted",
            finding_id=finding.id,
            techniques=len(finding.mitre_techniques),
            cves=len(finding.cve_ids),
        )

    async def persist_edge(self, edge: GraphEdge) -> None:
        """Persist a single GraphEdge into Neo4j.

        The source and target must already exist as nodes (or the
        relationship write will fail silently — MATCH requires existing nodes).

        Args:
            edge: The ``GraphEdge`` to persist.

        Raises:
            GraphStoreError: On Neo4j write failure.
        """
        props: dict = {}
        if edge.technique:
            props["technique"] = edge.technique
        if edge.weight != 1.0:
            props["weight"] = edge.weight

        await self._graph.upsert_relationship(
            rel_type=edge.relation,
            source_label="Finding",
            source_id=edge.source,
            target_label="Finding",
            target_id=edge.target,
            properties=props,
        )
        log.debug(
            "graph_builder.edge_persisted",
            relation=edge.relation,
            source=edge.source,
            target=edge.target,
        )

    async def persist_engagement_state(self, state: EngagementState) -> None:
        """Bulk-persist all findings and edges from an EngagementState.

        Args:
            state: The full engagement state after a phase or session.
        """
        for finding in state.findings:
            await self.persist_finding(finding, state.target)

        for edge in state.attack_graph:
            try:
                await self.persist_edge(edge)
            except GraphStoreError:
                log.warning(
                    "graph_builder.edge_skipped",
                    source=edge.source,
                    target=edge.target,
                )

        log.info(
            "graph_builder.state_persisted",
            findings=len(state.findings),
            edges=len(state.attack_graph),
        )

    async def link_cves_to_techniques(self, cve_cwe_map: dict[str, list[str]]) -> int:
        """Cross-link CVE nodes to Technique nodes based on CWE mappings.

        Args:
            cve_cwe_map: Dict mapping CVE IDs to their CWE IDs.
                         (e.g. ``{"CVE-2021-44228": ["CWE-502"]}``).

        Returns:
            Number of edges created.
        """
        # Static CWE → Technique mapping (subset, extendable)
        cwe_to_techniques: dict[str, list[str]] = {
            "CWE-79": ["T1059.007"],  # XSS → JS interpreter
            "CWE-89": ["T1190"],  # SQL injection → exploit public-facing app
            "CWE-502": ["T1059"],  # Unsafe deserialization → scripting
            "CWE-78": ["T1059"],  # OS command injection → scripting
            "CWE-22": ["T1083"],  # Path traversal → file/dir discovery
            "CWE-287": ["T1110"],  # Auth bypass → brute force
        }

        created = 0
        for cve_id, cwe_ids in cve_cwe_map.items():
            for cwe_id in cwe_ids:
                for tech_id in cwe_to_techniques.get(cwe_id.upper(), []):
                    try:
                        await self._graph.upsert_relationship(
                            "EXPLOITS_CVE", "Technique", tech_id, "CVE", cve_id
                        )
                        created += 1
                    except GraphStoreError:
                        pass  # Missing nodes — skip silently

        log.info("graph_builder.cve_links_created", count=created)
        return created
