"""Unit tests for MachineLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from seraph.benchmarks.loader import MachineLoader
from seraph.exceptions import MachineLoadError

# ── Fixtures ──────────────────────────────────────────────────────────────────

_VALID_YAML = """\
machines:
  - name: Lame
    ip: 10.10.10.3
    os: Linux
    difficulty: Easy
    flags:
      user: "<hash>"
      root: "<hash>"
    expected_techniques:
      - T1210
  - name: Blue
    ip: 10.10.10.40
    os: Windows
    difficulty: Easy
    flags:
      user: "<hash>"
      root: "<hash>"
    expected_techniques:
      - T1210
  - name: Reel
    ip: 10.10.10.143
    os: Windows
    difficulty: Hard
    flags:
      user: "<hash>"
      root: "<hash>"
    expected_techniques: []
"""


@pytest.fixture()
def machines_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "machines.yaml"
    p.write_text(_VALID_YAML)
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_load_all_returns_all_machines(machines_yaml: Path) -> None:
    loader = MachineLoader(machines_path=machines_yaml)
    specs = loader.load_all()
    assert len(specs) == 3
    assert {s.name for s in specs} == {"Lame", "Blue", "Reel"}


def test_load_by_name_case_insensitive(machines_yaml: Path) -> None:
    loader = MachineLoader(machines_path=machines_yaml)
    spec = loader.load_by_name("lame")
    assert spec.name == "Lame"
    assert spec.ip == "10.10.10.3"


def test_load_by_name_missing_raises(machines_yaml: Path) -> None:
    loader = MachineLoader(machines_path=machines_yaml)
    with pytest.raises(MachineLoadError, match="not found"):
        loader.load_by_name("NonExistent")


def test_load_by_difficulty_filters(machines_yaml: Path) -> None:
    loader = MachineLoader(machines_path=machines_yaml)
    easy = loader.load_by_difficulty("Easy")
    assert len(easy) == 2
    assert all(s.difficulty == "Easy" for s in easy)


def test_load_missing_file_raises() -> None:
    loader = MachineLoader(machines_path=Path("/nonexistent/machines.yaml"))
    with pytest.raises(MachineLoadError, match="not found"):
        loader.load_all()
