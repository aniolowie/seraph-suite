"""Integration tests for MITRE ATT&CK ingestion against real Neo4j."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.integration

# ── Mini STIX fixture ─────────────────────────────────────────────────────────

_MINI_STIX = {
    "type": "bundle",
    "id": "bundle--integration-test",
    "spec_version": "2.1",
    "objects": [
        {
            "id": "x-mitre-tactic--ta0002",
            "type": "x-mitre-tactic",
            "name": "Execution",
            "x_mitre_shortname": "execution",
            "description": "Execution tactic.",
            "external_references": [{"source_name": "mitre-attack", "external_id": "TA0002"}],
        },
        {
            "id": "x-mitre-tactic--ta0001",
            "type": "x-mitre-tactic",
            "name": "Initial Access",
            "x_mitre_shortname": "initial-access",
            "description": "Initial access tactic.",
            "external_references": [{"source_name": "mitre-attack", "external_id": "TA0001"}],
        },
        {
            "id": "attack-pattern--t1059",
            "type": "attack-pattern",
            "name": "Command Scripting",
            "description": "Adversaries abuse scripting interpreters.",
            "x_mitre_is_subtechnique": False,
            "x_mitre_platforms": ["Linux", "Windows"],
            "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "execution"}],
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1059"}],
        },
        {
            "id": "attack-pattern--t1059-001",
            "type": "attack-pattern",
            "name": "PowerShell",
            "description": "Adversaries abuse PowerShell.",
            "x_mitre_is_subtechnique": True,
            "x_mitre_platforms": ["Windows"],
            "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "execution"}],
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1059.001"}],
        },
        {
            "id": "attack-pattern--t1190",
            "type": "attack-pattern",
            "name": "Exploit Public-Facing App",
            "description": "Adversaries exploit public-facing applications.",
            "x_mitre_is_subtechnique": False,
            "x_mitre_platforms": ["Linux", "Windows"],
            "kill_chain_phases": [
                {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}
            ],
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1190"}],
        },
        {
            "id": "course-of-action--m1036",
            "type": "course-of-action",
            "name": "Account Use Policies",
            "description": "Configure account policies.",
            "external_references": [{"source_name": "mitre-attack", "external_id": "M1036"}],
        },
        {
            "id": "relationship--mitigates-1",
            "type": "relationship",
            "relationship_type": "mitigates",
            "source_ref": "course-of-action--m1036",
            "target_ref": "attack-pattern--t1059",
        },
        {
            "id": "relationship--sub-1",
            "type": "relationship",
            "relationship_type": "subtechnique-of",
            "source_ref": "attack-pattern--t1059-001",
            "target_ref": "attack-pattern--t1059",
        },
    ],
}


@pytest.fixture
async def mitre_ingestor(neo4j_store, tmp_path: Path, ingestion_db):  # type: ignore[no-untyped-def]
    """Provide a MITREIngestor with mini STIX fixture and mocked vector store."""
    from seraph.ingestion.mitre import MITREIngestor

    stix_file = tmp_path / "mini.json"
    stix_file.write_text(json.dumps(_MINI_STIX))

    dense = AsyncMock()
    dense.embed_texts = AsyncMock(return_value=[[0.1] * 768, [0.1] * 768, [0.1] * 768])
    sparse = AsyncMock()
    sparse.embed_texts = AsyncMock(
        return_value=[
            MagicMock(indices=[0], values=[1.0]),
            MagicMock(indices=[0], values=[1.0]),
            MagicMock(indices=[0], values=[1.0]),
        ]
    )
    vector_store = AsyncMock()
    vector_store.upsert_chunks = AsyncMock()

    return MITREIngestor(
        graph_store=neo4j_store,
        dense_embedder=dense,
        sparse_embedder=sparse,
        vector_store=vector_store,
        state_db=ingestion_db,
        stix_path=stix_file,
    )


class TestMITREIngestionEndToEnd:
    @pytest.mark.asyncio
    async def test_ingest_creates_tactic_nodes(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        count = await neo4j_store.count_nodes("Tactic")
        assert count == 2

    @pytest.mark.asyncio
    async def test_ingest_creates_technique_nodes(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        count = await neo4j_store.count_nodes("Technique")
        assert count == 3  # T1059, T1059.001, T1190

    @pytest.mark.asyncio
    async def test_ingest_creates_mitigation_nodes(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        count = await neo4j_store.count_nodes("Mitigation")
        assert count == 1

    @pytest.mark.asyncio
    async def test_ingest_technique_properties(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        node = await neo4j_store.get_node("Technique", "T1059")
        assert node is not None
        assert node["name"] == "Command Scripting"
        assert "Linux" in node.get("platforms", [])

    @pytest.mark.asyncio
    async def test_ingest_creates_mitigates_relationship(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        # Verify via Cypher query directly
        driver = neo4j_store._get_driver()
        async with driver.session() as session:
            result = await session.run(
                "MATCH (m:Mitigation)-[:MITIGATES]->(t:Technique) RETURN m.id AS mid, t.id AS tid"
            )
            records = await result.data()
        assert any(r["mid"] == "M1036" and r["tid"] == "T1059" for r in records)

    @pytest.mark.asyncio
    async def test_ingest_creates_uses_technique_relationship(
        self, mitre_ingestor, neo4j_store
    ) -> None:
        await mitre_ingestor.ingest()
        driver = neo4j_store._get_driver()
        async with driver.session() as session:
            result = await session.run(
                "MATCH (ta:Tactic)-[:USES_TECHNIQUE]->(t:Technique {id: 'T1059'}) "
                "RETURN ta.id AS tactic_id"
            )
            records = await result.data()
        assert any(r["tactic_id"] == "TA0002" for r in records)

    @pytest.mark.asyncio
    async def test_second_ingest_is_idempotent(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        await mitre_ingestor.ingest()  # second call should skip
        count = await neo4j_store.count_nodes("Technique")
        assert count == 3  # not doubled

    @pytest.mark.asyncio
    async def test_force_reingest_replaces_nodes(self, mitre_ingestor, neo4j_store) -> None:
        await mitre_ingestor.ingest()
        count_before = await neo4j_store.count_nodes("Technique")

        await mitre_ingestor.ingest(force=True)
        count_after = await neo4j_store.count_nodes("Technique")

        assert count_before == count_after  # same data, not doubled
