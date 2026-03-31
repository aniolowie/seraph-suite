"""Unit tests for machine registry routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from seraph.api.app import create_app
from seraph.api.deps import get_machine_loader, get_settings
from seraph.benchmarks.models import MachineSpec
from seraph.config import Settings
from seraph.exceptions import MachineLoadError


def _spec(name: str = "Lame") -> MachineSpec:
    return MachineSpec(
        name=name,
        ip="10.10.10.3",
        os="Linux",
        difficulty="Easy",
        flags={"user": "<hash>", "root": "<hash>"},
        expected_techniques=["T1210"],
    )


@pytest.fixture()
def client() -> TestClient:
    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(anthropic_api_key="test", neo4j_password="test")

    mock_loader = MagicMock()
    mock_loader.load_all.return_value = [_spec("Lame"), _spec("Blue")]
    mock_loader.load_by_name.return_value = _spec("Lame")

    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_machine_loader] = lambda: mock_loader
    return TestClient(app, raise_server_exceptions=False)


# ── list_machines ─────────────────────────────────────────────────────────────


def test_list_machines_returns_all(client: TestClient) -> None:
    response = client.get("/api/machines")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {m["name"] for m in data}
    assert "Lame" in names and "Blue" in names


def test_list_machines_has_real_flags_field(client: TestClient) -> None:
    response = client.get("/api/machines")
    assert response.status_code == 200
    for machine in response.json():
        assert "has_real_flags" in machine


# ── get_machine ───────────────────────────────────────────────────────────────


def test_get_machine_found(client: TestClient) -> None:
    response = client.get("/api/machines/Lame")
    assert response.status_code == 200
    assert response.json()["name"] == "Lame"
    assert response.json()["ip"] == "10.10.10.3"


def test_get_machine_not_found() -> None:
    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(anthropic_api_key="test", neo4j_password="test")

    mock_loader = MagicMock()
    mock_loader.load_by_name.side_effect = MachineLoadError("Machine 'X' not found")

    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_machine_loader] = lambda: mock_loader

    c = TestClient(app, raise_server_exceptions=False)
    response = c.get("/api/machines/nonexistent")
    assert response.status_code == 404


# ── add_machine ───────────────────────────────────────────────────────────────


def test_add_machine_creates_entry(tmp_path: Path) -> None:
    """POST /api/machines writes to machines.yaml and returns 201."""
    from seraph.api.routes.machines import _DEFAULT_MACHINES_PATH
    import seraph.api.routes.machines as machines_mod

    # Temporarily redirect the default path to a temp file.
    original = machines_mod._DEFAULT_MACHINES_PATH
    machines_mod._DEFAULT_MACHINES_PATH = tmp_path / "machines.yaml"
    (tmp_path / "machines.yaml").write_text("machines: []\n")

    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(anthropic_api_key="test", neo4j_password="test")

    mock_loader = MagicMock()
    mock_loader.load_all.return_value = []

    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_machine_loader] = lambda: mock_loader

    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.post(
            "/api/machines",
            json={
                "name": "TestBox",
                "ip": "10.10.10.99",
                "os": "Linux",
                "difficulty": "Easy",
                "expected_techniques": ["T1210"],
            },
        )
        assert response.status_code == 201
        assert response.json()["name"] == "TestBox"

        # Verify it was written to disk.
        import yaml

        data = yaml.safe_load((tmp_path / "machines.yaml").read_text())
        names = [m["name"] for m in data["machines"]]
        assert "TestBox" in names
    finally:
        machines_mod._DEFAULT_MACHINES_PATH = original


def test_add_machine_invalid_difficulty() -> None:
    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(anthropic_api_key="test", neo4j_password="test")

    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/machines",
        json={"name": "X", "ip": "10.0.0.1", "os": "Linux", "difficulty": "Trivial"},
    )
    assert response.status_code == 422
