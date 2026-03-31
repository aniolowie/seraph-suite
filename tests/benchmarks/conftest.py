"""Shared fixtures for HTB benchmark tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def htb_machines() -> list[dict]:
    """Load machine definitions from machines.yaml."""
    from pathlib import Path

    import yaml

    machines_file = Path(__file__).parent / "machines.yaml"
    with machines_file.open() as f:
        data = yaml.safe_load(f)
    return data.get("machines", [])
