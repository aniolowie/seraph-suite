"""Unit tests for ingestion Pydantic models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from seraph.ingestion.models import DocumentChunk, IngestionRecord


class TestDocumentChunk:
    def test_minimal_creation(self) -> None:
        chunk = DocumentChunk(id="cve-001", text="some text", source="nvd", doc_type="cve")
        assert chunk.id == "cve-001"
        assert chunk.metadata == {}

    def test_with_metadata(self) -> None:
        chunk = DocumentChunk(
            id="cve-001",
            text="[CVE-2021-44228] Apache Log4j2...",
            source="nvd",
            doc_type="cve",
            metadata={"cve_id": "CVE-2021-44228", "cvss_score": 10.0, "severity": "CRITICAL"},
        )
        assert chunk.metadata["cvss_score"] == 10.0

    def test_immutability_by_convention(self) -> None:
        """model_copy should produce a new instance, not mutate."""
        chunk = DocumentChunk(id="a", text="x", source="nvd", doc_type="cve")
        new_chunk = chunk.model_copy(update={"text": "y"})
        assert chunk.text == "x"
        assert new_chunk.text == "y"

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            DocumentChunk(text="x", source="nvd", doc_type="cve")  # type: ignore[call-arg]


class TestIngestionRecord:
    def test_default_status_is_ok(self) -> None:
        record = IngestionRecord(source_id="CVE-2021-44228", source="nvd")
        assert record.status == "ok"
        assert record.chunk_count == 0
        assert record.error == ""

    def test_custom_fields(self) -> None:
        record = IngestionRecord(
            source_id="12345",
            source="exploitdb",
            chunk_count=3,
            status="ok",
        )
        assert record.chunk_count == 3

    def test_ingested_at_defaults_to_now(self) -> None:
        before = datetime.utcnow()
        record = IngestionRecord(source_id="x", source="nvd")
        after = datetime.utcnow()
        assert before <= record.ingested_at <= after

    def test_failed_record(self) -> None:
        record = IngestionRecord(source_id="x", source="nvd", status="failed", error="timeout")
        assert record.status == "failed"
        assert record.error == "timeout"
