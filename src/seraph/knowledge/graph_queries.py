"""Cypher traversal query library for the Seraph attack graph.

These read-only queries are used by the GraphRAG retriever to enrich
vector search results with structured graph context.  All write operations
live in ``graphstore.py``.
"""

from __future__ import annotations

from typing import Any

import structlog

from seraph.exceptions import GraphStoreError
from seraph.knowledge.graph_models import MitigationNode, TechniqueNode

log = structlog.get_logger(__name__)


class GraphQueryLibrary:
    """Read-only traversal queries for the attack graph.

    Composes with ``Neo4jStore`` — accepts the store's driver session
    indirectly via the store's ``_get_driver()`` method.

    Args:
        store: A ``Neo4jStore`` instance (provides the async driver).
    """

    def __init__(self, store: Any) -> None:
        """Initialise with a Neo4jStore instance."""
        self._store = store

    async def find_techniques_for_cve(self, cve_id: str) -> list[TechniqueNode]:
        """Return Technique nodes linked to a CVE via EXPLOITS_CVE.

        Args:
            cve_id: CVE identifier (e.g. ``"CVE-2021-44228"``).

        Returns:
            List of matching ``TechniqueNode`` objects.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = (
            "MATCH (t:Technique)-[:EXPLOITS_CVE]->(c:CVE {id: $cve_id}) "
            "RETURN properties(t) AS props"
        )
        return await self._query_techniques(cypher, cve_id=cve_id)

    async def find_techniques_by_name(self, name_fragment: str) -> list[TechniqueNode]:
        """Full-text search for techniques by name fragment (case-insensitive).

        Args:
            name_fragment: Partial technique name.

        Returns:
            List of matching ``TechniqueNode`` objects.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = (
            "MATCH (t:Technique) "
            "WHERE toLower(t.name) CONTAINS toLower($fragment) "
            "RETURN properties(t) AS props "
            "LIMIT 20"
        )
        return await self._query_techniques(cypher, fragment=name_fragment)

    async def find_related_techniques(
        self, technique_id: str, depth: int = 2
    ) -> list[TechniqueNode]:
        """Traverse up to ``depth`` hops from a technique via structural edges.

        Traverses: SUBTECHNIQUE_OF (both directions), USES (inbound from
        Group/Software — i.e. techniques used alongside this one).

        Args:
            technique_id: MITRE technique ID (e.g. ``"T1059"``).
            depth: Maximum traversal depth (capped at 3 for safety).

        Returns:
            List of related ``TechniqueNode`` objects (excludes the seed).

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        depth = min(depth, 3)
        cypher = (
            "MATCH (seed:Technique {id: $tid}) "
            "MATCH (seed)-[:SUBTECHNIQUE_OF*0.." + str(depth) + "]-(related:Technique) "
            "WHERE related.id <> $tid "
            "RETURN DISTINCT properties(related) AS props "
            "LIMIT 20"
        )
        return await self._query_techniques(cypher, tid=technique_id)

    async def find_mitigations_for_technique(self, technique_id: str) -> list[MitigationNode]:
        """Return Mitigation nodes that target a technique.

        Args:
            technique_id: MITRE technique ID.

        Returns:
            List of ``MitigationNode`` objects.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = (
            "MATCH (m:Mitigation)-[:MITIGATES]->(t:Technique {id: $tid}) "
            "RETURN properties(m) AS props"
        )
        try:
            driver = self._store._get_driver()
            async with driver.session() as session:
                result = await session.run(cypher, tid=technique_id)
                records = await result.data()
            return [
                MitigationNode(**{k: v for k, v in r["props"].items() if v is not None})
                for r in records
            ]
        except Exception as exc:
            raise GraphStoreError(
                f"find_mitigations_for_technique failed for {technique_id}: {exc}"
            ) from exc

    async def find_techniques_for_tactic(self, tactic_id: str) -> list[TechniqueNode]:
        """Return all Technique nodes that belong to a Tactic.

        Args:
            tactic_id: MITRE tactic ID (e.g. ``"TA0002"``).

        Returns:
            List of ``TechniqueNode`` objects.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = (
            "MATCH (ta:Tactic {id: $tactic_id})-[:USES_TECHNIQUE]->(t:Technique) "
            "RETURN properties(t) AS props"
        )
        return await self._query_techniques(cypher, tactic_id=tactic_id)

    async def get_technique_context(self, technique_id: str) -> dict:
        """Return a rich context bundle for a technique — for LLM prompts.

        Includes: technique properties, parent tactic, mitigations, and
        software that uses the technique.

        Args:
            technique_id: MITRE technique ID.

        Returns:
            Dict with keys ``technique``, ``tactic``, ``mitigations``,
            ``software`` — values are dicts/lists of node properties.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = """
        MATCH (t:Technique {id: $tid})
        OPTIONAL MATCH (ta:Tactic)-[:USES_TECHNIQUE]->(t)
        OPTIONAL MATCH (m:Mitigation)-[:MITIGATES]->(t)
        OPTIONAL MATCH (s:Software)-[:USES]->(t)
        RETURN
            properties(t) AS technique,
            collect(DISTINCT properties(ta)) AS tactics,
            collect(DISTINCT properties(m)) AS mitigations,
            collect(DISTINCT properties(s)) AS software
        """
        try:
            driver = self._store._get_driver()
            async with driver.session() as session:
                result = await session.run(cypher, tid=technique_id)
                record = await result.single()
            if record is None:
                return {}
            return {
                "technique": dict(record["technique"]) if record["technique"] else {},
                "tactics": [dict(ta) for ta in record["tactics"] if ta],
                "mitigations": [dict(m) for m in record["mitigations"] if m],
                "software": [dict(s) for s in record["software"] if s],
            }
        except Exception as exc:
            raise GraphStoreError(
                f"get_technique_context failed for {technique_id}: {exc}"
            ) from exc

    async def list_all_technique_names(self) -> list[dict[str, str]]:
        """Return id+name for all Technique nodes (for entity extraction cache).

        Returns:
            List of ``{"id": "T1059", "name": "Command Scripting"}`` dicts.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = "MATCH (t:Technique) RETURN t.id AS id, t.name AS name ORDER BY t.id"
        try:
            driver = self._store._get_driver()
            async with driver.session() as session:
                result = await session.run(cypher)
                records = await result.data()
            return [{"id": r["id"], "name": r["name"]} for r in records]
        except Exception as exc:
            raise GraphStoreError(f"list_all_technique_names failed: {exc}") from exc

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _query_techniques(self, cypher: str, **params: Any) -> list[TechniqueNode]:
        """Run a Cypher query returning technique props and deserialise.

        Args:
            cypher: Cypher query that returns ``props`` column.
            **params: Query parameters.

        Returns:
            List of ``TechniqueNode`` objects.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        try:
            driver = self._store._get_driver()
            async with driver.session() as session:
                result = await session.run(cypher, **params)
                records = await result.data()
            nodes = []
            for r in records:
                props = {k: v for k, v in r["props"].items() if v is not None}
                # platforms may be stored as a string in older ingestion — normalise
                if isinstance(props.get("platforms"), str):
                    props["platforms"] = [props["platforms"]]
                if isinstance(props.get("tactic_ids"), str):
                    props["tactic_ids"] = [props["tactic_ids"]]
                nodes.append(TechniqueNode(**props))
            return nodes
        except GraphStoreError:
            raise
        except Exception as exc:
            raise GraphStoreError(f"Technique query failed: {exc}") from exc
