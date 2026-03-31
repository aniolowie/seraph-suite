"""Machine definition loader for the HTB benchmarking harness.

Reads ``tests/benchmarks/machines.yaml`` and returns typed ``MachineSpec``
objects, with optional filtering by name or difficulty.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import structlog

from seraph.benchmarks.models import MachineSpec
from seraph.exceptions import MachineLoadError

log = structlog.get_logger(__name__)

# Default path relative to the project root.
_DEFAULT_MACHINES_PATH = Path("tests/benchmarks/machines.yaml")


class MachineLoader:
    """Loads and filters HTB machine definitions from YAML.

    Args:
        machines_path: Path to the machines YAML file.
            Defaults to ``tests/benchmarks/machines.yaml``.
    """

    def __init__(self, machines_path: Path | None = None) -> None:
        self._path = machines_path or _DEFAULT_MACHINES_PATH

    def load_all(self) -> list[MachineSpec]:
        """Load every machine defined in the YAML file.

        Returns:
            List of ``MachineSpec`` objects in definition order.

        Raises:
            MachineLoadError: If the file is missing or malformed.
        """
        raw = self._read_yaml()
        machines_data = raw.get("machines", [])
        if not isinstance(machines_data, list):
            raise MachineLoadError(
                f"'machines' key in {self._path} must be a list, got {type(machines_data)}"
            )
        specs: list[MachineSpec] = []
        for entry in machines_data:
            try:
                specs.append(MachineSpec(**entry))
            except Exception as exc:
                raise MachineLoadError(
                    f"Invalid machine entry {entry!r}: {exc}"
                ) from exc
        log.info("benchmark.loader.loaded", count=len(specs), path=str(self._path))
        return specs

    def load_by_name(self, name: str) -> MachineSpec:
        """Return the spec for a single machine by name (case-insensitive).

        Args:
            name: Machine name, e.g. ``"Lame"``.

        Returns:
            The matching ``MachineSpec``.

        Raises:
            MachineLoadError: If no machine with that name exists.
        """
        for spec in self.load_all():
            if spec.name.lower() == name.lower():
                return spec
        raise MachineLoadError(
            f"Machine {name!r} not found in {self._path}. "
            "Check the spelling or add it to machines.yaml."
        )

    def load_by_difficulty(
        self,
        difficulty: Literal["Easy", "Medium", "Hard", "Insane"],
    ) -> list[MachineSpec]:
        """Return all machines matching the given difficulty.

        Args:
            difficulty: One of ``"Easy"``, ``"Medium"``, ``"Hard"``, ``"Insane"``.

        Returns:
            Filtered list of ``MachineSpec`` objects (may be empty).
        """
        specs = [s for s in self.load_all() if s.difficulty == difficulty]
        log.info(
            "benchmark.loader.filtered",
            difficulty=difficulty,
            count=len(specs),
        )
        return specs

    # ── Internal ──────────────────────────────────────────────────────────────

    def _read_yaml(self) -> dict:
        """Read and parse the YAML file.

        Returns:
            Parsed dict.

        Raises:
            MachineLoadError: On missing file or parse error.
        """
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MachineLoadError("PyYAML is required: pip install pyyaml") from exc

        if not self._path.exists():
            raise MachineLoadError(
                f"Machines file not found: {self._path}. "
                "Create it or set a custom path."
            )
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception as exc:
            raise MachineLoadError(
                f"Failed to parse {self._path}: {exc}"
            ) from exc
