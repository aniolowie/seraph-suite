"""Neo4j async client for the Seraph attack graph.

Provides CRUD operations (MERGE/MATCH) against the Neo4j CE graph database.
Higher-level traversal queries live in ``graph_queries.py``.

Usage::

    store = Neo4jStore()
    await store.ensure_schema()
    await store.upsert_node("Technique", "T1059", {"name": "Command Scripting"})
    await store.close()
"""

from __future__ import annotations

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase

from seraph.config import settings
from seraph.exceptions import GraphStoreError
from seraph.knowledge.graph_models import GraphRelationship

log = structlog.get_logger(__name__)

# Unique constraint definitions: (label, property)
_CONSTRAINTS: list[tuple[str, str]] = [
    ("Tactic", "id"),
    ("Technique", "id"),
    ("Mitigation", "id"),
    ("Software", "id"),
    ("Group", "id"),
    ("DataSource", "id"),
    ("CVE", "id"),
    ("Finding", "id"),
    ("Host", "ip"),
]

# Index definitions for text search: (label, property)
_INDEXES: list[tuple[str, str]] = [
    ("Technique", "name"),
    ("CVE", "id"),
    ("Host", "ip"),
]


class Neo4jStore:
    """Async Neo4j client with MERGE-based upsert operations.

    All methods are async and use the Neo4j async driver.  The driver is
    created lazily on first use to support test injection.

    Args:
        uri: Bolt URI for the Neo4j instance.
        user: Neo4j username.
        password: Neo4j password.
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialise the store with connection parameters."""
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver: AsyncDriver | None = None

    def _get_driver(self) -> AsyncDriver:
        """Return (or lazily create) the async Neo4j driver."""
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(self._uri, auth=(self._user, self._password))
        return self._driver

    async def ensure_schema(self) -> None:
        """Create uniqueness constraints and indexes idempotently.

        Safe to call on every startup — uses ``IF NOT EXISTS`` syntax
        (Neo4j 4.4+).

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        driver = self._get_driver()
        try:
            async with driver.session() as session:
                for label, prop in _CONSTRAINTS:
                    cname = f"constraint_{label.lower()}_{prop}"
                    cypher = (
                        f"CREATE CONSTRAINT {cname} IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
                    )
                    await session.run(cypher)
                for label, prop in _INDEXES:
                    iname = f"index_{label.lower()}_{prop}"
                    cypher = f"CREATE INDEX {iname} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
                    await session.run(cypher)
            log.info("graphstore.schema_ensured")
        except Exception as exc:
            raise GraphStoreError(f"ensure_schema failed: {exc}") from exc

    async def upsert_node(self, label: str, node_id: str, properties: dict) -> None:
        """MERGE a single node by label + id, then SET all properties.

        Args:
            label: Neo4j node label (e.g. ``"Technique"``).
            node_id: The ``id`` property value used as the merge key.
            properties: Additional properties to set on the node.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        driver = self._get_driver()
        props = {**properties, "id": node_id}
        cypher = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
        try:
            async with driver.session() as session:
                await session.run(cypher, id=node_id, props=props)
        except Exception as exc:
            raise GraphStoreError(f"upsert_node failed for {label}:{node_id}: {exc}") from exc

    async def upsert_nodes_batch(self, label: str, nodes: list[dict]) -> None:
        """Batch MERGE nodes using UNWIND for efficiency.

        Args:
            label: Neo4j node label.
            nodes: List of property dicts, each must contain an ``"id"`` key.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        if not nodes:
            return
        cypher = f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row"
        try:
            driver = self._get_driver()
            async with driver.session() as session:
                await session.run(cypher, rows=nodes)
            log.debug("graphstore.batch_upsert", label=label, count=len(nodes))
        except Exception as exc:
            raise GraphStoreError(f"upsert_nodes_batch failed for {label}: {exc}") from exc

    async def upsert_relationship(
        self,
        rel_type: str,
        source_label: str,
        source_id: str,
        target_label: str,
        target_id: str,
        properties: dict | None = None,
    ) -> None:
        """MERGE a relationship between two nodes.

        Args:
            rel_type: Relationship type (e.g. ``"MITIGATES"``).
            source_label: Neo4j label of the source node.
            source_id: ``id`` of the source node.
            target_label: Neo4j label of the target node.
            target_id: ``id`` of the target node.
            properties: Optional properties to set on the relationship.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        props = properties or {}
        cypher = (
            f"MATCH (a:{source_label} {{id: $src_id}}) "
            f"MATCH (b:{target_label} {{id: $tgt_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props"
        )
        try:
            driver = self._get_driver()
            async with driver.session() as session:
                await session.run(cypher, src_id=source_id, tgt_id=target_id, props=props)
        except Exception as exc:
            raise GraphStoreError(
                f"upsert_relationship {source_label}-[{rel_type}]->{target_label} failed: {exc}"
            ) from exc

    async def upsert_relationships_batch(self, relationships: list[GraphRelationship]) -> None:
        """Batch MERGE relationships grouped by type.

        Groups relationships by (rel_type, source_label, target_label) and
        issues one UNWIND query per group for performance.

        Args:
            relationships: List of ``GraphRelationship`` objects.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        if not relationships:
            return
        # Group by (rel_type, source_label, target_label)
        groups: dict[tuple[str, str, str], list[GraphRelationship]] = {}
        for rel in relationships:
            key = (rel.rel_type, rel.source_label, rel.target_label)
            groups.setdefault(key, []).append(rel)

        driver = self._get_driver()
        try:
            async with driver.session() as session:
                for (rel_type, src_lbl, tgt_lbl), rels in groups.items():
                    rows = [
                        {"src_id": r.source_id, "tgt_id": r.target_id, "props": r.properties}
                        for r in rels
                    ]
                    cypher = (
                        f"UNWIND $rows AS row "
                        f"MATCH (a:{src_lbl} {{id: row.src_id}}) "
                        f"MATCH (b:{tgt_lbl} {{id: row.tgt_id}}) "
                        f"MERGE (a)-[r:{rel_type}]->(b) "
                        f"SET r += row.props"
                    )
                    await session.run(cypher, rows=rows)
            log.debug("graphstore.batch_upsert_rels", count=len(relationships))
        except GraphStoreError:
            raise
        except Exception as exc:
            raise GraphStoreError(f"upsert_relationships_batch failed: {exc}") from exc

    async def get_node(self, label: str, node_id: str) -> dict | None:
        """Fetch a single node by label and id.

        Args:
            label: Neo4j node label.
            node_id: The node's ``id`` property.

        Returns:
            Dict of node properties, or ``None`` if not found.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = f"MATCH (n:{label} {{id: $id}}) RETURN properties(n) AS props"
        try:
            driver = self._get_driver()
            async with driver.session() as session:
                result = await session.run(cypher, id=node_id)
                record = await result.single()
                return dict(record["props"]) if record else None
        except Exception as exc:
            raise GraphStoreError(f"get_node failed for {label}:{node_id}: {exc}") from exc

    async def delete_nodes_by_label(self, label: str) -> None:
        """Delete all nodes (and their relationships) with the given label.

        Used by ``--force`` re-ingestion.

        Args:
            label: Neo4j node label to delete.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = f"MATCH (n:{label}) DETACH DELETE n"
        try:
            driver = self._get_driver()
            async with driver.session() as session:
                await session.run(cypher)
            log.info("graphstore.deleted_by_label", label=label)
        except Exception as exc:
            raise GraphStoreError(f"delete_nodes_by_label failed for {label}: {exc}") from exc

    async def count_nodes(self, label: str) -> int:
        """Count nodes with the given label.

        Args:
            label: Neo4j node label.

        Returns:
            Node count.

        Raises:
            GraphStoreError: On Neo4j query failure.
        """
        cypher = f"MATCH (n:{label}) RETURN count(n) AS cnt"
        try:
            driver = self._get_driver()
            async with driver.session() as session:
                result = await session.run(cypher)
                record = await result.single()
                return int(record["cnt"]) if record else 0
        except Exception as exc:
            raise GraphStoreError(f"count_nodes failed for {label}: {exc}") from exc

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            log.debug("graphstore.closed")
