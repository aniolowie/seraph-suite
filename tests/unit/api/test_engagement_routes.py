"""Unit tests for engagement monitoring routes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from seraph.api.app import create_app
from seraph.api.deps import get_settings
from seraph.api.routes.engagements import _registry, register_engagement, unregister_engagement
from seraph.config import Settings


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    """Ensure the in-memory registry is empty before and after each test."""
    _registry.clear()
    yield
    _registry.clear()


@pytest.fixture()
def client() -> TestClient:
    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(anthropic_api_key="test", neo4j_password="test")

    app.dependency_overrides[get_settings] = _fake_settings
    return TestClient(app, raise_server_exceptions=False)


def _sample_state() -> dict:
    return {
        "target_ip": "10.10.10.3",
        "target_os": "Linux",
        "phase": "recon",
        "flags": [],
        "findings": [{"type": "open_port", "port": 22}],
        "tool_outputs": [],
        "plan": [],
        "started_at": datetime.now(UTC).isoformat(),
        "_wall_start": 0.0,
    }


# ── list_engagements ──────────────────────────────────────────────────────────


def test_list_engagements_empty(client: TestClient) -> None:
    response = client.get("/api/engagements")
    assert response.status_code == 200
    assert response.json() == []


def test_list_engagements_returns_summaries(client: TestClient) -> None:
    register_engagement("bench-lame-abc", _sample_state())
    response = client.get("/api/engagements")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["engagement_id"] == "bench-lame-abc"
    assert data[0]["phase"] == "recon"


def test_list_engagements_multiple(client: TestClient) -> None:
    register_engagement("eng-1", _sample_state())
    register_engagement("eng-2", {**_sample_state(), "phase": "exploit"})
    response = client.get("/api/engagements")
    assert response.status_code == 200
    assert len(response.json()) == 2


# ── get_engagement ────────────────────────────────────────────────────────────


def test_get_engagement_not_found(client: TestClient) -> None:
    response = client.get("/api/engagements/nonexistent")
    assert response.status_code == 404


def test_get_engagement_returns_detail(client: TestClient) -> None:
    register_engagement("bench-lame-abc", _sample_state())
    response = client.get("/api/engagements/bench-lame-abc")
    assert response.status_code == 200
    data = response.json()
    assert data["engagement_id"] == "bench-lame-abc"
    assert data["target_ip"] == "10.10.10.3"
    assert len(data["findings"]) == 1


# ── register / unregister helpers ────────────────────────────────────────────


def test_unregister_removes_engagement(client: TestClient) -> None:
    register_engagement("bench-lame-abc", _sample_state())
    unregister_engagement("bench-lame-abc")
    response = client.get("/api/engagements/bench-lame-abc")
    assert response.status_code == 404


def test_unregister_missing_no_error() -> None:
    unregister_engagement("does-not-exist")  # should not raise
