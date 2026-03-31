"""Machine registry routes.

GET    /api/machines         — list all registered machines
GET    /api/machines/{name}  — single machine detail
POST   /api/machines         — add a new machine to machines.yaml
DELETE /api/machines/{name}  — remove a machine from machines.yaml
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml
from fastapi import APIRouter, HTTPException

from seraph.api.deps import MachineLoaderDep
from seraph.api.schemas import MachineCreateRequest, MachineResponse
from seraph.benchmarks.models import MachineSpec
from seraph.exceptions import MachineLoadError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/machines", tags=["machines"])

# Default machines.yaml path (matches MachineLoader default).
_DEFAULT_MACHINES_PATH = Path("tests/benchmarks/machines.yaml")


def _spec_to_response(spec: MachineSpec) -> MachineResponse:
    return MachineResponse(
        name=spec.name,
        ip=spec.ip,
        os=spec.os,
        difficulty=spec.difficulty,
        expected_techniques=spec.expected_techniques,
        has_real_flags=spec.has_real_flags,
    )


def _load_yaml(path: Path) -> dict:
    """Load raw machines YAML; return empty structure if missing."""
    if not path.exists():
        return {"machines": []}
    return yaml.safe_load(path.read_text()) or {"machines": []}


def _save_yaml_atomic(path: Path, data: dict) -> None:
    """Write YAML to a temp file then rename atomically.

    Args:
        path: Target YAML file path.
        data: Data to serialise.
    """
    tmp = path.with_suffix(".yaml.tmp")
    try:
        tmp.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True))
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[MachineResponse], summary="List machines")
async def list_machines(loader: MachineLoaderDep) -> list[MachineResponse]:
    """Return all machines from the registry."""
    try:
        specs = loader.load_all()  # type: ignore[attr-defined]
    except MachineLoadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return [_spec_to_response(s) for s in specs]


@router.get("/{name}", response_model=MachineResponse, summary="Single machine")
async def get_machine(name: str, loader: MachineLoaderDep) -> MachineResponse:
    """Return a single machine by name (case-insensitive).

    Args:
        name: Machine name (e.g. ``Lame``).

    Raises:
        HTTPException: 404 if the machine is not found.
    """
    try:
        spec = loader.load_by_name(name)  # type: ignore[attr-defined]
    except MachineLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _spec_to_response(spec)


@router.post("", response_model=MachineResponse, status_code=201, summary="Add machine")
async def add_machine(body: MachineCreateRequest) -> MachineResponse:
    """Append a new machine to machines.yaml.

    Args:
        body: Machine definition (name, IP, OS, difficulty, techniques).

    Raises:
        HTTPException: 409 if a machine with the same name already exists.
    """
    path = _DEFAULT_MACHINES_PATH
    data = _load_yaml(path)
    machines: list[dict] = data.get("machines", [])

    if any(m.get("name", "").lower() == body.name.lower() for m in machines):
        raise HTTPException(
            status_code=409,
            detail=f"Machine '{body.name}' already exists",
        )

    new_entry = {
        "name": body.name,
        "ip": body.ip,
        "os": body.os,
        "difficulty": body.difficulty,
        "flags": {"user": "<hash>", "root": "<hash>"},
        "expected_techniques": body.expected_techniques,
    }
    machines.append(new_entry)
    data["machines"] = machines

    try:
        _save_yaml_atomic(path, data)
    except Exception as exc:
        log.error("machines.save_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to save machines.yaml: {exc}") from exc

    spec = MachineSpec(
        name=body.name,
        ip=body.ip,
        os=body.os,
        difficulty=body.difficulty,
        flags={"user": "<hash>", "root": "<hash>"},
        expected_techniques=body.expected_techniques,
    )
    log.info("machines.added", name=body.name)
    return _spec_to_response(spec)


@router.delete("/{name}", status_code=204, summary="Remove machine")
async def delete_machine(name: str) -> None:
    """Remove a machine from machines.yaml by name.

    Args:
        name: Machine name to remove (case-insensitive).

    Raises:
        HTTPException: 404 if the machine is not found.
    """
    path = _DEFAULT_MACHINES_PATH
    data = _load_yaml(path)
    machines: list[dict] = data.get("machines", [])
    original_count = len(machines)

    machines = [m for m in machines if m.get("name", "").lower() != name.lower()]
    if len(machines) == original_count:
        raise HTTPException(status_code=404, detail=f"Machine '{name}' not found")

    data["machines"] = machines
    try:
        _save_yaml_atomic(path, data)
    except Exception as exc:
        log.error("machines.delete_save_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to save machines.yaml: {exc}") from exc

    log.info("machines.deleted", name=name)
