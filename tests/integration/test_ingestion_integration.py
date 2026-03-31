"""End-to-end integration tests for the ingestion pipeline.

Tests the full flow: parse → embed (real models) → upsert → retrieve.
Requires: docker compose up -d (Qdrant on localhost:6333)
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


# Minimal NVD API v2 response fixture.
_NVD_FIXTURE = [
    {
        "cve": {
            "id": f"CVE-2024-9999{i}",
            "descriptions": [
                {"lang": "en", "value": f"Test vulnerability number {i} in test software."}
            ],
            "metrics": {
                "cvssMetricV31": [{"cvssData": {"baseScore": float(i + 5), "baseSeverity": "HIGH"}}]
            },
            "weaknesses": [{"description": [{"lang": "en", "value": "CWE-79"}]}],
            "published": "2024-01-01T00:00:00.000",
        }
    }
    for i in range(3)
]


class TestNVDIngestionIntegration:
    async def test_nvd_ingest_and_retrieve(
        self, qdrant_store: object, ingestion_db: object
    ) -> None:
        from seraph.ingestion.nvd import NVDIngestor
        from seraph.ingestion.state import IngestionStateDB
        from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        db: IngestionStateDB = ingestion_db  # type: ignore[assignment]

        dense = DenseEmbedder()
        sparse = SparseEmbedder()

        ingestor = NVDIngestor(
            dense_embedder=dense,
            sparse_embedder=sparse,
            vector_store=store,
            state_db=db,
        )

        async def fake_fetch(**kwargs: object):  # type: ignore[return]
            for v in _NVD_FIXTURE:
                yield v

        with patch.object(ingestor, "fetch_cves", return_value=fake_fetch()):
            count = await ingestor.ingest()

        assert count == 3
        assert await store.count() == 3

    async def test_nvd_idempotency(self, qdrant_store: object, ingestion_db: object) -> None:
        from seraph.ingestion.nvd import NVDIngestor
        from seraph.ingestion.state import IngestionStateDB
        from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        db: IngestionStateDB = ingestion_db  # type: ignore[assignment]

        ingestor = NVDIngestor(
            dense_embedder=DenseEmbedder(),
            sparse_embedder=SparseEmbedder(),
            vector_store=store,
            state_db=db,
        )

        async def fake_fetch(**kwargs: object):  # type: ignore[return]
            for v in _NVD_FIXTURE[:1]:
                yield v

        with patch.object(ingestor, "fetch_cves", return_value=fake_fetch()):
            count1 = await ingestor.ingest()

        with patch.object(ingestor, "fetch_cves", return_value=fake_fetch()):
            count2 = await ingestor.ingest()

        assert count1 == 1
        assert count2 == 0  # already ingested
        assert await store.count() == 1


class TestExploitDBIngestionIntegration:
    async def test_exploitdb_ingest(
        self, qdrant_store: object, ingestion_db: object, tmp_path: Path
    ) -> None:
        from seraph.ingestion.exploitdb import ExploitDBIngestor
        from seraph.ingestion.state import IngestionStateDB
        from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
        from seraph.knowledge.vectorstore import QdrantStore

        store: QdrantStore = qdrant_store  # type: ignore[assignment]
        db: IngestionStateDB = ingestion_db  # type: ignore[assignment]

        # Build a minimal ExploitDB mirror structure.
        exploits_dir = tmp_path / "exploits" / "remote"
        exploits_dir.mkdir(parents=True)

        for i in range(3):
            exploit_file = exploits_dir / f"exploit_{i}.py"
            exploit_file.write_text(
                dedent(f"""\
                    # Exploit Title: Test Exploit {i}
                    # Author: researcher
                    # CVE: CVE-2024-1234{i}

                    import socket
                    payload = b'\\x90' * 100
                """)
            )

        # Create a minimal CSV index.
        csv_path = tmp_path / "files_exploits.csv"
        csv_path.write_text(
            "id,file,description,date_published,author,platform,type,port\n"
            + "\n".join(
                f"{i},exploits/remote/exploit_{i}.py,Test exploit {i},"
                f"2024-01-0{i + 1},researcher,Linux,remote,80"
                for i in range(3)
            )
            + "\n"
        )

        ingestor = ExploitDBIngestor(
            dense_embedder=DenseEmbedder(),
            sparse_embedder=SparseEmbedder(),
            vector_store=store,
            state_db=db,
        )

        count = await ingestor.ingest(mirror_path=tmp_path)
        assert count == 3
        assert await store.count() == 3
