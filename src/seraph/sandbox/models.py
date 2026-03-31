"""Pydantic models for the Docker sandbox layer.

All models are immutable by convention — use ``model.model_copy(update={...})``
rather than mutating in place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ContainerStatus(StrEnum):
    """Lifecycle state of a managed sandbox container."""

    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    REMOVED = "removed"
    ERROR = "error"


class ContainerSpec(BaseModel):
    """Specification for creating a sandbox container.

    Passed to ``ContainerManager.create_container()`` to describe the
    desired container configuration.
    """

    agent_name: str = Field(description="Seraph agent that owns this container.")
    image: str = Field(description="Docker image name:tag to run.")
    tools: list[str] = Field(
        default_factory=list,
        description="Tool names to mount (informational; controls which binaries are available).",
    )
    target_ip: str = Field(default="", description="Engagement target IP for network scoping.")
    cpu_limit: float = Field(
        default=1.0,
        ge=0.1,
        le=8.0,
        description="CPU core limit (Docker cpu_quota derived from this).",
    )
    memory_limit_mb: int = Field(
        default=512,
        ge=64,
        le=8192,
        description="Container memory limit in MiB.",
    )
    timeout_seconds: int = Field(
        default=3600,
        ge=60,
        le=14400,
        description="Wall-clock lifetime of the container.",
    )
    network_name: str = Field(default="", description="Docker network to attach the container to.")
    volumes: dict[str, str] = Field(
        default_factory=dict,
        description="Volume mount mapping: {host_path: container_path[:options]}.",
    )
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables injected into the container.",
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Docker labels applied to the container.",
    )


class ContainerInfo(BaseModel):
    """Runtime information about a managed sandbox container."""

    container_id: str
    agent_name: str
    status: ContainerStatus
    ip_address: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    spec: ContainerSpec


class ExecResult(BaseModel):
    """Raw output from a ``docker exec`` invocation."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    command: str = ""


class PooledContainer(BaseModel):
    """A container tracked by the ContainerPool."""

    container_id: str
    agent_name: str
    leased: bool = False
    leased_at: datetime | None = None
    spec: ContainerSpec

    model_config = {"arbitrary_types_allowed": True}
