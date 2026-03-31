"""Pydantic models for the self-learning loop.

All data structures are immutable by convention — produce new instances via
``model.model_copy(update={...})`` rather than mutating in place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class FeedbackRecord(BaseModel):
    """One retrieval event logged during an engagement.

    Tracks which documents were retrieved for a query and which were
    actually cited by the LLM in its final response.  This diff (retrieved
    but not cited) is the raw material for hard negative mining.
    """

    id: str = Field(description="Unique record ID (UUID or engagement+seq).")
    engagement_id: str
    agent_name: str
    query: str
    retrieved_doc_ids: list[str] = Field(default_factory=list)
    cited_doc_ids: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Triplet(BaseModel):
    """A (query, positive, hard_negative) training triplet.

    Used as input to the InfoNCE / contrastive fine-tuning loss.
    Text fields hold the actual chunk text so training does not need to
    look them up from the vector store.
    """

    query: str
    positive_doc_id: str
    negative_doc_id: str
    positive_text: str
    negative_text: str
    source: str = Field(
        default="feedback",
        description="Origin of the triplet: 'feedback' | 'synthetic'.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrainingConfig(BaseModel):
    """Hyperparameters for a single LoRA training run."""

    lora_rank: int = 8
    lora_alpha: int = 16
    target_modules: list[str] = Field(default_factory=lambda: ["query", "key", "value"])
    batch_size: int = 16
    epochs: int = 3
    learning_rate: float = 2e-4
    adapter_output_dir: Path = Path("./data/models/lora_adapters/latest")


class TrainingResult(BaseModel):
    """Outcome of a completed LoRA training run."""

    adapter_path: Path
    triplets_used: int
    final_loss: float
    duration_seconds: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    success: bool = True
    error_message: str = ""
