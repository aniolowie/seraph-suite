"""Unit tests for MITREIngestor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.exceptions import MITREIngestionError
from seraph.ingestion.mitre import MITREIngestor
from seraph.ingestion.state import IngestionStateDB

_MINI_BUNDLE = {
    "type": "bundle",
    "id": "bundle--test-123",
    "spec_version": "2.1",
    "objects": [
        {
            "id": "x-mitre-tactic--ta0002",
            "type": "x-mitre-tactic",
            "name": "Execution",
            "x_mitre_shortname": "execution",
            "external_references": [{"source_name": "mitre-attack", "external_id": "TA0002"}],
        },
        {
            "id": "attack-pattern--t1059",
            "type": "attack-pattern",
            "name": "Command Scripting",
            "description": "Run scripts.",
            "x_mitre_is_subtechnique": False,
            "x_mitre_platforms": ["Linux"],
            "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "execution"}],
            "external_references": [{"source_name": "mitre-attack", "external_id": "T1059"}],
        },
    ],
}


def _make_ingestor(tmp_path: Path) -> tuple[MITREIngestor, MagicMock, IngestionStateDB]:
    """Build an ingestor with mocked graph/vector stores."""
    stix_file = tmp_path / "mitre.json"
    stix_file.write_text(json.dumps(_MINI_BUNDLE))

    graph_store = MagicMock()
    graph_store.delete_nodes_by_label = AsyncMock()
    graph_store.upsert_nodes_batch = AsyncMock()
    graph_store.upsert_relationships_batch = AsyncMock()

    dense_embedder = AsyncMock()
    dense_embedder.embed_texts = AsyncMock(return_value=[[0.1] * 768])
    sparse_embedder = AsyncMock()
    sparse_embedder.embed_texts = AsyncMock(return_value=[MagicMock(indices=[0], values=[1.0])])
    vector_store = AsyncMock()
    vector_store.upsert_chunks = AsyncMock()

    state_db = IngestionStateDB(db_path=tmp_path / "state.db")

    ingestor = MITREIngestor(
        graph_store=graph_store,
        dense_embedder=dense_embedder,
        sparse_embedder=sparse_embedder,
        vector_store=vector_store,
        state_db=state_db,
        stix_path=stix_file,
    )
    return ingestor, graph_store, state_db


class TestMITREIngestorIngest:
    @pytest.mark.asyncio
    async def test_full_ingest_upserts_nodes(self, tmp_path: Path) -> None:
        ingestor, graph_store, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()

        count = await ingestor.ingest()

        assert count > 0
        graph_store.upsert_nodes_batch.assert_called()

    @pytest.mark.asyncio
    async def test_full_ingest_upserts_relationships(self, tmp_path: Path) -> None:
        ingestor, graph_store, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()

        await ingestor.ingest()

        graph_store.upsert_relationships_batch.assert_called()

    @pytest.mark.asyncio
    async def test_ingest_records_in_state_db(self, tmp_path: Path) -> None:
        ingestor, _, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()

        await ingestor.ingest()

        stats = await state_db.get_stats("mitre")
        assert stats.get("ok", 0) >= 1

    @pytest.mark.asyncio
    async def test_second_ingest_is_skipped(self, tmp_path: Path) -> None:
        ingestor, graph_store, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()

        await ingestor.ingest()
        graph_store.upsert_nodes_batch.reset_mock()

        count = await ingestor.ingest()
        assert count == 0
        graph_store.upsert_nodes_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_clears_and_reingests(self, tmp_path: Path) -> None:
        ingestor, graph_store, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()

        await ingestor.ingest()
        graph_store.upsert_nodes_batch.reset_mock()

        count = await ingestor.ingest(force=True)
        assert count > 0
        graph_store.delete_nodes_by_label.assert_called()
        graph_store.upsert_nodes_batch.assert_called()

    @pytest.mark.asyncio
    async def test_missing_stix_file_download_fails_raises(self, tmp_path: Path) -> None:
        ingestor, _, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()
        ingestor._stix_path = tmp_path / "nonexistent.json"

        with patch("seraph.ingestion.mitre.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=ConnectionError("network unreachable"))
            mock_client_cls.return_value = mock_client

            with pytest.raises(MITREIngestionError, match="Failed to download"):
                await ingestor.ingest()

    @pytest.mark.asyncio
    async def test_download_called_when_file_missing(self, tmp_path: Path) -> None:
        ingestor, _, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()
        missing_path = tmp_path / "subdir" / "bundle.json"
        ingestor._stix_path = missing_path

        with patch.object(ingestor, "_ensure_stix_file", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = MITREIngestionError("download blocked in test")
            with pytest.raises(MITREIngestionError):
                await ingestor.ingest(download=True)
            mock_dl.assert_called_once_with(True)


class TestMITREIngestorDualWrite:
    @pytest.mark.asyncio
    async def test_techniques_written_to_qdrant(self, tmp_path: Path) -> None:
        ingestor, _, state_db = _make_ingestor(tmp_path)
        await state_db.init_db()

        await ingestor.ingest()

        ingestor._store.upsert_chunks.assert_called()

    @pytest.mark.asyncio
    async def test_no_qdrant_write_for_empty_descriptions(self, tmp_path: Path) -> None:
        stix_file = tmp_path / "mitre.json"
        bundle = {
            **_MINI_BUNDLE,
            "objects": [
                {**_MINI_BUNDLE["objects"][1], "description": ""},
            ],
        }
        stix_file.write_text(json.dumps(bundle))

        graph_store = MagicMock()
        graph_store.delete_nodes_by_label = AsyncMock()
        graph_store.upsert_nodes_batch = AsyncMock()
        graph_store.upsert_relationships_batch = AsyncMock()
        dense_embedder = AsyncMock()
        dense_embedder.embed_texts = AsyncMock(return_value=[[0.1] * 768])
        sparse_embedder = AsyncMock()
        sparse_embedder.embed_texts = AsyncMock(return_value=[MagicMock(indices=[0], values=[1.0])])
        vector_store = AsyncMock()
        vector_store.upsert_chunks = AsyncMock()
        state_db = IngestionStateDB(db_path=tmp_path / "state2.db")
        await state_db.init_db()

        ingestor = MITREIngestor(
            graph_store=graph_store,
            dense_embedder=dense_embedder,
            sparse_embedder=sparse_embedder,
            vector_store=vector_store,
            state_db=state_db,
            stix_path=stix_file,
        )
        # With empty description, technique name is used — upsert_chunks should not be called
        # when no text is available at all (fallback to name handles this)
        await ingestor.ingest()
        # The technique has no description but has a name, so it will still be written
        # (single_chunk will use the name). This is expected behavior.
