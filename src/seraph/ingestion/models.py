"""Pydantic data models for the ingestion pipeline.

These are immutable DTOs — create new instances, never mutate in-place.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A single chunk of text ready to be embedded and upserted into Qdrant.

    The ``text`` field is what gets embedded. Metadata fields go into the
    Qdrant point payload for filtering — they are NOT embedded.
    """

    id: str = Field(..., description="Unique chunk ID (e.g. 'CVE-2021-44228-0')")
    text: str = Field(..., description="Text to embed (includes source tag prefix)")
    source: str = Field(..., description="Source name: 'nvd', 'exploitdb', 'writeup'")
    doc_type: str = Field(..., description="Document type: 'cve', 'exploit', 'writeup'")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Payload fields for Qdrant filtering (not embedded)",
    )


class IngestionRecord(BaseModel):
    """Tracks ingestion state in SQLite for idempotency.

    ``source_id`` is the canonical ID in the source system (e.g. CVE ID,
    EDB-ID). Combined with ``source``, it forms the primary key.
    """

    source_id: str
    source: str  # 'nvd', 'exploitdb', 'writeup', etc.
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    chunk_count: int = Field(default=0, ge=0)
    status: str = Field(default="ok")  # 'ok' | 'failed'
    error: str = Field(default="")
