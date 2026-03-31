"""Unit tests for writeup submission routes."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from seraph.api.app import create_app
from seraph.api.deps import get_settings
from seraph.config import Settings


@pytest.fixture()
def client(tmp_path: object) -> TestClient:
    app = create_app()

    def _fake_settings() -> Settings:
        return Settings(anthropic_api_key="test", neo4j_password="test")

    app.dependency_overrides[get_settings] = _fake_settings
    return TestClient(app, raise_server_exceptions=False)


def _md_file(content: str = "# Lame\nThis is a writeup.") -> tuple[str, io.BytesIO, str]:
    return ("file", io.BytesIO(content.encode()), "text/markdown")


# ── submit_writeup ────────────────────────────────────────────────────────────


def test_submit_writeup_accepted(client: TestClient, tmp_path: Path) -> None:
    # The route writes to ./data/writeups — create that dir under tmp_path and
    # patch the constant string so it lands there instead.
    import seraph.api.routes.writeups as wu_mod

    writes_dir = tmp_path / "writeups"
    writes_dir.mkdir()

    original_path_cls = wu_mod.Path

    def _fake_path(s: str) -> Path:
        if str(s) == "./data/writeups":
            return writes_dir
        return original_path_cls(s)

    with patch.object(wu_mod, "Path", side_effect=_fake_path):
        response = client.post(
            "/api/writeups",
            files={"file": ("lame.md", io.BytesIO(b"# Lame writeup"), "text/markdown")},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["filename"].endswith(".md")
    assert "task_id" in data
    assert "/api/writeups/status/" in data["status_url"]


def test_submit_writeup_too_large(client: TestClient) -> None:
    big_content = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/api/writeups",
        files={"file": ("big.md", io.BytesIO(big_content), "text/markdown")},
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


def test_submit_writeup_wrong_content_type(client: TestClient) -> None:
    response = client.post(
        "/api/writeups",
        files={"file": ("exploit.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert response.status_code == 400


def test_submit_writeup_script_injection(client: TestClient) -> None:
    malicious = b"# Writeup\n<script>alert(1)</script>"
    response = client.post(
        "/api/writeups",
        files={"file": ("evil.md", io.BytesIO(malicious), "text/markdown")},
    )
    assert response.status_code == 400
    assert "disallowed" in response.json()["detail"].lower()


# ── task_status ───────────────────────────────────────────────────────────────


def test_task_status_unknown_when_celery_unavailable(client: TestClient) -> None:
    with patch("celery.result.AsyncResult", side_effect=Exception("celery down")):
        response = client.get("/api/writeups/status/fake-task-id")
    assert response.status_code == 200
    assert response.json()["state"] in ("UNKNOWN", "PENDING")
