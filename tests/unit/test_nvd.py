"""Unit tests for NVDIngestor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.ingestion.nvd import (
    NVDIngestor,
    _extract_cvss,
    _extract_cwe_ids,
    _extract_english_description,
)

# ── Fixture data ──────────────────────────────────────────────────────────────

_CVE_FULL = {
    "cve": {
        "id": "CVE-2021-44228",
        "descriptions": [
            {"lang": "en", "value": "Apache Log4j2 2.0-beta9 through 2.14.1 JNDI features..."},
            {"lang": "es", "value": "Versión española..."},
        ],
        "metrics": {
            "cvssMetricV31": [
                {
                    "cvssData": {
                        "baseScore": 10.0,
                        "baseSeverity": "CRITICAL",
                    }
                }
            ]
        },
        "weaknesses": [
            {"description": [{"lang": "en", "value": "CWE-400"}]},
            {"description": [{"lang": "en", "value": "CWE-20"}]},
        ],
        "published": "2021-12-10T10:15:09.143",
    }
}

_CVE_NO_CVSS = {
    "cve": {
        "id": "CVE-2022-99999",
        "descriptions": [{"lang": "en", "value": "Some vulnerability."}],
        "metrics": {},
        "weaknesses": [],
        "published": "2022-01-01T00:00:00.000",
    }
}

_CVE_NO_DESCRIPTION = {
    "cve": {
        "id": "CVE-2022-11111",
        "descriptions": [],
        "metrics": {},
        "weaknesses": [],
        "published": "2022-01-01",
    }
}


# ── Helper tests ──────────────────────────────────────────────────────────────


class TestExtractHelpers:
    def test_extract_english_description(self) -> None:
        desc = _extract_english_description(_CVE_FULL["cve"])
        assert "Log4j2" in desc

    def test_extract_description_no_english(self) -> None:
        cve = {"descriptions": [{"lang": "es", "value": "hola"}]}
        assert _extract_english_description(cve) == ""

    def test_extract_cvss_v31(self) -> None:
        score, severity = _extract_cvss(_CVE_FULL["cve"])
        assert score == pytest.approx(10.0)
        assert severity == "CRITICAL"

    def test_extract_cvss_missing(self) -> None:
        score, severity = _extract_cvss(_CVE_NO_CVSS["cve"])
        assert score == 0.0
        assert severity == "UNKNOWN"

    def test_extract_cwe_ids(self) -> None:
        ids = _extract_cwe_ids(_CVE_FULL["cve"])
        assert ids == ["CWE-400", "CWE-20"]

    def test_extract_cwe_empty(self) -> None:
        assert _extract_cwe_ids({"weaknesses": []}) == []


# ── NVDIngestor tests ─────────────────────────────────────────────────────────


def _make_ingestor() -> NVDIngestor:
    return NVDIngestor(
        dense_embedder=AsyncMock(),
        sparse_embedder=AsyncMock(),
        vector_store=AsyncMock(),
        state_db=AsyncMock(),
    )


class TestNVDIngestor:
    def test_parse_cve_full(self) -> None:
        ingestor = _make_ingestor()
        chunk = ingestor.parse_cve(_CVE_FULL)
        assert chunk is not None
        assert chunk.id == "CVE-2021-44228-0"
        assert "[CVE-2021-44228]" in chunk.text
        assert chunk.metadata["cve_id"] == "CVE-2021-44228"
        assert chunk.metadata["cvss_score"] == pytest.approx(10.0)
        assert chunk.metadata["severity"] == "CRITICAL"
        assert "CWE-400" in chunk.metadata["cwe_ids"]
        assert chunk.source == "nvd"
        assert chunk.doc_type == "cve"

    def test_parse_cve_no_description_returns_none(self) -> None:
        ingestor = _make_ingestor()
        assert ingestor.parse_cve(_CVE_NO_DESCRIPTION) is None

    def test_parse_cve_no_cvss_defaults_to_zero(self) -> None:
        ingestor = _make_ingestor()
        chunk = ingestor.parse_cve(_CVE_NO_CVSS)
        assert chunk is not None
        assert chunk.metadata["cvss_score"] == 0.0

    def test_parse_cve_missing_id_returns_none(self) -> None:
        ingestor = _make_ingestor()
        assert ingestor.parse_cve({"cve": {}}) is None

    async def test_ingest_skips_already_ingested(self) -> None:
        ingestor = _make_ingestor()
        ingestor._state_db.init_db = AsyncMock()
        ingestor._store.ensure_collection = AsyncMock()
        ingestor._state_db.is_ingested = AsyncMock(return_value=True)

        # Patch fetch_cves to yield one CVE.
        async def fake_fetch(**kwargs: object):  # type: ignore[return]
            yield _CVE_FULL

        with patch.object(ingestor, "fetch_cves", return_value=fake_fetch()):
            count = await ingestor.ingest()

        assert count == 0
        ingestor._store.upsert_chunks.assert_not_awaited()

    async def test_ingest_processes_new_cves(self) -> None:
        ingestor = _make_ingestor()
        ingestor._state_db.init_db = AsyncMock()
        ingestor._store.ensure_collection = AsyncMock()
        ingestor._state_db.is_ingested = AsyncMock(return_value=False)
        ingestor._state_db.mark_ingested = AsyncMock()
        ingestor._dense.embed_texts = AsyncMock(return_value=[[0.1] * 768])
        ingestor._sparse.embed_texts = AsyncMock(
            return_value=[MagicMock(indices=[1], values=[0.5])]
        )
        ingestor._store.upsert_chunks = AsyncMock()

        async def fake_fetch(**kwargs: object):  # type: ignore[return]
            yield _CVE_FULL

        with patch.object(ingestor, "fetch_cves", return_value=fake_fetch()):
            count = await ingestor.ingest()

        assert count == 1
