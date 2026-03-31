"""Unit tests for sandbox Pydantic models."""

from __future__ import annotations

from datetime import datetime

import pytest

from seraph.sandbox.models import (
    ContainerInfo,
    ContainerSpec,
    ContainerStatus,
    ExecResult,
    PooledContainer,
)


def test_container_spec_defaults() -> None:
    spec = ContainerSpec(agent_name="recon", image="seraph-agent:latest")
    assert spec.cpu_limit == 1.0
    assert spec.memory_limit_mb == 512
    assert spec.timeout_seconds == 3600
    assert spec.tools == []
    assert spec.volumes == {}
    assert spec.environment == {}
    assert spec.labels == {}


def test_container_spec_cpu_validation() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContainerSpec(agent_name="x", image="img", cpu_limit=0.0)  # below ge=0.1


def test_container_info_created_at_default() -> None:
    spec = ContainerSpec(agent_name="a", image="img")
    info = ContainerInfo(
        container_id="abc123",
        agent_name="a",
        status=ContainerStatus.CREATED,
        spec=spec,
    )
    assert isinstance(info.created_at, datetime)
    assert info.created_at.tzinfo is not None
    assert info.ip_address == ""


def test_exec_result_fields() -> None:
    result = ExecResult(
        exit_code=0,
        stdout="hello",
        stderr="",
        duration_seconds=0.5,
        timed_out=False,
        command="echo hello",
    )
    assert result.exit_code == 0
    assert result.stdout == "hello"
    assert not result.timed_out


def test_pooled_container_defaults() -> None:
    spec = ContainerSpec(agent_name="pool-0", image="img")
    pooled = PooledContainer(
        container_id="cid123",
        agent_name="pool-0",
        spec=spec,
    )
    assert pooled.leased is False
    assert pooled.leased_at is None


def test_container_status_values() -> None:
    assert ContainerStatus.RUNNING == "running"
    assert ContainerStatus.STOPPED == "stopped"
    assert ContainerStatus.ERROR == "error"
