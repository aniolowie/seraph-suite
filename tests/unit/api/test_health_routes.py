"""Unit tests for GET /api/health and GET /api/readyz."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from seraph.api.app import create_app
from seraph.api.deps import get_qdrant_client, get_settings
from seraph.config import Settings


@pytest.fixture()
def client() -> TestClient:
    """TestClient with mocked settings (no real external services)."""
    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(
            anthropic_api_key="test",
            neo4j_password="test",
            cors_origins=["http://localhost:5173"],
        )

    async def _fake_qdrant():  # noqa: ANN202
        mock = AsyncMock()
        mock.get_collections = AsyncMock(return_value=[])
        yield mock

    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_qdrant_client] = _fake_qdrant
    return TestClient(app, raise_server_exceptions=False)


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["services"] == []


def test_readyz_with_all_services_up(client: TestClient) -> None:
    with (
        patch("seraph.api.routes.health.redis.asyncio.from_url") as mock_redis_factory,
        patch("seraph.api.routes.health.AsyncGraphDatabase.driver") as mock_neo4j,
    ):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.aclose = AsyncMock()
        mock_redis_factory.return_value = mock_redis

        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_neo4j.return_value = mock_driver

        response = client.get("/api/readyz")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    service_names = {s["name"] for s in data["services"]}
    assert "qdrant" in service_names
    assert "redis" in service_names
    assert "neo4j" in service_names


def test_readyz_degraded_when_redis_down(client: TestClient) -> None:
    with (
        patch(
            "seraph.api.routes.health.redis.asyncio.from_url",
            side_effect=ConnectionRefusedError("refused"),
        ),
        patch("seraph.api.routes.health.AsyncGraphDatabase.driver") as mock_neo4j,
    ):
        mock_driver = AsyncMock()
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_neo4j.return_value = mock_driver

        response = client.get("/api/readyz")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    redis_status = next(s for s in data["services"] if s["name"] == "redis")
    assert not redis_status["ok"]
