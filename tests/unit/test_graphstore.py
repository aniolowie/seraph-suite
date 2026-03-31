"""Unit tests for Neo4jStore and GraphQueryLibrary."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.exceptions import GraphStoreError
from seraph.knowledge.graph_models import GraphRelationship
from seraph.knowledge.graphstore import Neo4jStore


def _make_store() -> Neo4jStore:
    return Neo4jStore(uri="bolt://localhost:7687", user="neo4j", password="test")


class TestNeo4jStoreInit:
    def test_defaults_from_settings(self) -> None:
        with patch("seraph.knowledge.graphstore.settings") as mock_settings:
            mock_settings.neo4j_uri = "bolt://localhost:7687"
            mock_settings.neo4j_user = "neo4j"
            mock_settings.neo4j_password = "password"
            store = Neo4jStore()
        assert store._uri == "bolt://localhost:7687"
        assert store._driver is None

    def test_explicit_params_override_settings(self) -> None:
        store = Neo4jStore(uri="bolt://custom:7687", user="u", password="p")
        assert store._uri == "bolt://custom:7687"
        assert store._user == "u"


class TestNeo4jStoreEnsureSchema:
    @pytest.mark.asyncio
    async def test_ensure_schema_runs_constraints_and_indexes(self) -> None:
        store = _make_store()
        mock_session = AsyncMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        await store.ensure_schema()

        # Should have called session.run at least once per constraint + index
        assert mock_session.run.call_count >= 9  # 9 constraints
        # Verify CREATE CONSTRAINT appears in calls
        calls = [str(c) for c in mock_session.run.call_args_list]
        assert any("CREATE CONSTRAINT" in c for c in calls)
        assert any("CREATE INDEX" in c for c in calls)

    @pytest.mark.asyncio
    async def test_ensure_schema_wraps_exception(self) -> None:
        store = _make_store()
        mock_driver = MagicMock()
        mock_driver.session.side_effect = RuntimeError("connection refused")
        store._driver = mock_driver

        with pytest.raises(GraphStoreError, match="ensure_schema failed"):
            await store.ensure_schema()


class TestNeo4jStoreUpsertNode:
    @pytest.mark.asyncio
    async def test_upsert_node_calls_merge(self) -> None:
        store = _make_store()
        mock_session = AsyncMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        await store.upsert_node("Technique", "T1059", {"name": "Command Scripting"})

        mock_session.run.assert_called_once()
        cypher = mock_session.run.call_args[0][0]
        assert "MERGE" in cypher
        assert "Technique" in cypher
        assert "SET" in cypher

    @pytest.mark.asyncio
    async def test_upsert_node_wraps_exception(self) -> None:
        store = _make_store()
        mock_driver = MagicMock()
        mock_driver.session.side_effect = RuntimeError("fail")
        store._driver = mock_driver

        with pytest.raises(GraphStoreError, match="upsert_node failed"):
            await store.upsert_node("Technique", "T1059", {})


class TestNeo4jStoreUpsertNodesBatch:
    @pytest.mark.asyncio
    async def test_batch_upsert_uses_unwind(self) -> None:
        store = _make_store()
        mock_session = AsyncMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        nodes = [{"id": "T1059", "name": "Cmd"}, {"id": "T1055", "name": "Inject"}]
        await store.upsert_nodes_batch("Technique", nodes)

        mock_session.run.assert_called_once()
        cypher = mock_session.run.call_args[0][0]
        assert "UNWIND" in cypher
        assert "MERGE" in cypher

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self) -> None:
        store = _make_store()
        store._driver = MagicMock()
        await store.upsert_nodes_batch("Technique", [])
        store._driver.session.assert_not_called()


class TestNeo4jStoreUpsertRelationship:
    @pytest.mark.asyncio
    async def test_upsert_relationship_calls_merge(self) -> None:
        store = _make_store()
        mock_session = AsyncMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        await store.upsert_relationship("MITIGATES", "Mitigation", "M1036", "Technique", "T1059")

        mock_session.run.assert_called_once()
        cypher = mock_session.run.call_args[0][0]
        assert "MERGE" in cypher
        assert "MITIGATES" in cypher


class TestNeo4jStoreUpsertRelationshipsBatch:
    @pytest.mark.asyncio
    async def test_batch_groups_by_type(self) -> None:
        store = _make_store()
        mock_session = AsyncMock()
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        rels = [
            GraphRelationship(
                rel_type="MITIGATES",
                source_label="Mitigation",
                source_id="M1036",
                target_label="Technique",
                target_id="T1059",
            ),
            GraphRelationship(
                rel_type="MITIGATES",
                source_label="Mitigation",
                source_id="M1037",
                target_label="Technique",
                target_id="T1055",
            ),
        ]
        await store.upsert_relationships_batch(rels)
        # Both same type → one UNWIND call
        assert mock_session.run.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self) -> None:
        store = _make_store()
        store._driver = MagicMock()
        await store.upsert_relationships_batch([])
        store._driver.session.assert_not_called()


class TestNeo4jStoreGetNode:
    @pytest.mark.asyncio
    async def test_get_node_returns_properties(self) -> None:
        store = _make_store()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"props": {"id": "T1059", "name": "Cmd"}})
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        result = await store.get_node("Technique", "T1059")
        assert result == {"id": "T1059", "name": "Cmd"}

    @pytest.mark.asyncio
    async def test_get_node_returns_none_when_not_found(self) -> None:
        store = _make_store()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_driver = MagicMock()
        mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
        store._driver = mock_driver

        result = await store.get_node("Technique", "T9999")
        assert result is None


class TestNeo4jStoreClose:
    @pytest.mark.asyncio
    async def test_close_calls_driver_close(self) -> None:
        store = _make_store()
        mock_driver = AsyncMock()
        store._driver = mock_driver

        await store.close()

        mock_driver.close.assert_called_once()
        assert store._driver is None

    @pytest.mark.asyncio
    async def test_close_noop_if_no_driver(self) -> None:
        store = _make_store()
        await store.close()  # should not raise
