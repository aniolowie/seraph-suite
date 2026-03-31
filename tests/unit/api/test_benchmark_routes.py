"""Unit tests for benchmark history and trigger routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seraph.api.app import create_app
from seraph.api.deps import get_settings
from seraph.config import Settings


def _fake_settings_factory(reports_dir: Path) -> Settings:
    return Settings(
        anthropic_api_key="test",
        neo4j_password="test",
        reports_dir=reports_dir,
    )


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _fake_settings_factory(tmp_path)
    return TestClient(app, raise_server_exceptions=False)


def _write_report(reports_dir: Path, run_id: str) -> None:
    """Write a minimal benchmark report JSON to disk."""
    data = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "results": [],
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{run_id}.json").write_text(json.dumps(data))


# ── list_benchmarks ───────────────────────────────────────────────────────────


def test_list_benchmarks_empty(client: TestClient, tmp_path: Path) -> None:
    response = client.get("/api/benchmarks")
    assert response.status_code == 200
    assert response.json() == []


def test_list_benchmarks_returns_runs(client: TestClient, tmp_path: Path) -> None:
    _write_report(tmp_path, "run-20250401-120000")
    _write_report(tmp_path, "run-20250402-120000")
    response = client.get("/api/benchmarks")
    assert response.status_code == 200
    assert len(response.json()) == 2


# ── get_benchmark ─────────────────────────────────────────────────────────────


def test_get_benchmark_not_found(client: TestClient) -> None:
    response = client.get("/api/benchmarks/run-99999999-000000")
    assert response.status_code == 404


def test_get_benchmark_found(client: TestClient, tmp_path: Path) -> None:
    run_id = "run-20250401-120000"
    _write_report(tmp_path, run_id)
    response = client.get(f"/api/benchmarks/{run_id}")
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id


# ── share_benchmark ───────────────────────────────────────────────────────────


def test_share_benchmark_returns_raw_json(client: TestClient, tmp_path: Path) -> None:
    run_id = "run-20250401-120000"
    _write_report(tmp_path, run_id)
    response = client.get(f"/api/benchmarks/{run_id}/share")
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id


def test_share_benchmark_not_found(client: TestClient) -> None:
    response = client.get("/api/benchmarks/run-missing/share")
    assert response.status_code == 404


# ── trigger_benchmark ─────────────────────────────────────────────────────────


def test_trigger_benchmark_no_target_returns_400(client: TestClient) -> None:
    response = client.post("/api/benchmarks", json={})
    assert response.status_code == 400


def test_trigger_benchmark_accepted(client: TestClient) -> None:
    """Trigger returns 202 even when Celery is unavailable (graceful fallback)."""
    response = client.post("/api/benchmarks", json={"machine": "Lame", "timeout_seconds": 3600})
    assert response.status_code == 202
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "accepted"
