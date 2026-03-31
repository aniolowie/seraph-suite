"""Unit tests for LoRAFineTuner (5 tests)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from seraph.exceptions import FinetuneError
from seraph.learning.finetune import LoRAFineTuner, _collate_fn
from seraph.learning.models import TrainingConfig


def test_collate_fn_groups_batch_correctly():
    """_collate_fn produces parallel query/positive/negative lists."""
    batch = [
        {"query": "q1", "positive_text": "p1", "negative_text": "n1"},
        {"query": "q2", "positive_text": "p2", "negative_text": "n2"},
    ]
    result = _collate_fn(batch)
    assert result["queries"] == ["q1", "q2"]
    assert result["positives"] == ["p1", "p2"]
    assert result["negatives"] == ["n1", "n2"]


@pytest.mark.asyncio
async def test_train_raises_on_empty_triplets(tmp_path):
    """LoRAFineTuner.train raises FinetuneError when given empty triplets."""
    tuner = LoRAFineTuner(adapter_dir=tmp_path)
    with pytest.raises(FinetuneError, match="empty"):
        await tuner.train([])


def test_training_config_defaults():
    """TrainingConfig has sensible defaults."""
    config = TrainingConfig()
    assert config.lora_rank == 8
    assert config.lora_alpha == 16
    assert config.epochs == 3
    assert config.learning_rate > 0


@pytest.mark.asyncio
async def test_train_calls_sync_in_thread(tmp_path):
    """LoRAFineTuner.train delegates to _train_sync via asyncio.to_thread."""
    from seraph.learning.models import TrainingResult

    tuner = LoRAFineTuner(adapter_dir=tmp_path)
    fake_result = TrainingResult(
        adapter_path=tmp_path / "latest",
        triplets_used=2,
        final_loss=0.1,
        duration_seconds=1.0,
    )
    with patch.object(tuner, "_train_sync", return_value=fake_result) as mock_sync:
        result = await tuner.train(
            [
                {"query": "q", "positive_text": "p", "negative_text": "n"},
            ]
        )
    mock_sync.assert_called_once()
    assert result.triplets_used == 2


@pytest.mark.asyncio
async def test_train_wraps_sync_exception_in_finetune_error(tmp_path):
    """Exceptions from _train_sync are wrapped in FinetuneError."""
    tuner = LoRAFineTuner(adapter_dir=tmp_path)
    with patch.object(tuner, "_train_sync", side_effect=RuntimeError("GPU OOM")):
        with pytest.raises(FinetuneError):
            await tuner.train([{"query": "q", "positive_text": "p", "negative_text": "n"}])
