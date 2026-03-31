"""Unit tests for QueryProjection (4 tests)."""

from __future__ import annotations

import pytest

from seraph.exceptions import ProjectionError
from seraph.learning.projection import QueryProjection


@pytest.fixture
def proj(tmp_path):
    """QueryProjection with a temporary model path (no pre-existing file)."""
    return QueryProjection(model_path=tmp_path / "proj.pt")


@pytest.mark.asyncio
async def test_project_returns_768d_vector(proj):
    """project() returns a 768-dimensional float list."""
    vector = [0.1] * 768
    result = await proj.project(vector)
    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)


@pytest.mark.asyncio
async def test_project_raises_on_wrong_dim(proj):
    """project() raises ProjectionError on incorrect input dimension."""
    with pytest.raises(ProjectionError, match="dim"):
        await proj.project([0.1] * 512)


@pytest.mark.asyncio
async def test_save_and_reload(tmp_path):
    """save() persists weights; reload() loads them back."""
    path = tmp_path / "proj.pt"
    proj = QueryProjection(model_path=path)

    # Trigger model init
    await proj.project([0.0] * 768)

    await proj.save()
    assert path.exists()

    proj2 = QueryProjection(model_path=path)
    result = await proj2.project([0.5] * 768)
    assert len(result) == 768


@pytest.mark.asyncio
async def test_reload_raises_when_file_missing(tmp_path):
    """reload() raises ProjectionError when the .pt file does not exist."""
    proj = QueryProjection(model_path=tmp_path / "missing.pt")
    with pytest.raises(ProjectionError, match="not found"):
        await proj.reload()
