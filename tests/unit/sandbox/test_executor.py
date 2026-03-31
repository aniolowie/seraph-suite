"""Unit tests for SandboxExecutor (all Docker calls mocked)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seraph.exceptions import CommandTimeoutError, SandboxError
from seraph.sandbox.executor import SandboxExecutor
from seraph.sandbox.models import ExecResult


@pytest.fixture()
def mock_docker() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def executor(mock_docker: MagicMock) -> SandboxExecutor:
    return SandboxExecutor(docker_client=mock_docker)


class _AsyncIter:
    """Async iterator over a list of (type, data) pairs."""

    def __init__(self, items: list[tuple[int, bytes]]) -> None:
        self._items = iter(items)

    def __aiter__(self) -> _AsyncIter:
        return self

    async def __anext__(self) -> tuple[int, bytes]:
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration from None


def _make_exec_mock(
    stdout_data: bytes = b"",
    stderr_data: bytes = b"",
    exit_code: int = 0,
) -> MagicMock:
    """Build a mock aiodocker exec object."""
    items: list[tuple[int, bytes]] = []
    if stdout_data:
        items.append((1, stdout_data))
    if stderr_data:
        items.append((2, stderr_data))

    @asynccontextmanager
    async def _start(*, detach: bool = False):
        yield _AsyncIter(items)

    fake_exec = MagicMock()
    fake_exec.start = _start
    fake_exec.inspect = AsyncMock(return_value={"ExitCode": exit_code})
    return fake_exec


@pytest.mark.asyncio
async def test_execute_command_success(executor: SandboxExecutor, mock_docker: MagicMock) -> None:
    """Happy path: command runs and returns ExecResult."""
    fake_exec = _make_exec_mock(stdout_data=b"output", exit_code=0)
    fake_container = MagicMock()
    fake_container.exec = AsyncMock(return_value=fake_exec)
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    result = await executor.execute_command("abc123def456", ["echo", "hi"])
    assert result.exit_code == 0
    assert result.stdout == "output"
    assert not result.timed_out


@pytest.mark.asyncio
async def test_execute_command_stderr(executor: SandboxExecutor, mock_docker: MagicMock) -> None:
    """Stderr is captured separately."""
    fake_exec = _make_exec_mock(stderr_data=b"err msg", exit_code=1)
    fake_container = MagicMock()
    fake_container.exec = AsyncMock(return_value=fake_exec)
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    result = await executor.execute_command("abc123def456", ["cat", "/missing"])
    assert result.exit_code == 1
    assert result.stderr == "err msg"


@pytest.mark.asyncio
async def test_execute_command_timeout(executor: SandboxExecutor, mock_docker: MagicMock) -> None:
    """Raises CommandTimeoutError when asyncio.wait_for expires."""

    with patch("seraph.sandbox.executor.asyncio.wait_for", side_effect=TimeoutError()):
        with pytest.raises(CommandTimeoutError):
            await executor.execute_command("cid123def456", ["sleep", "9999"], timeout=1)


@pytest.mark.asyncio
async def test_execute_command_docker_error(
    executor: SandboxExecutor, mock_docker: MagicMock
) -> None:
    """Unexpected Docker errors wrapped as SandboxError."""
    with patch(
        "seraph.sandbox.executor.asyncio.wait_for",
        side_effect=RuntimeError("docker crashed"),
    ):
        with pytest.raises(SandboxError, match="docker crashed"):
            await executor.execute_command("cid123def456", ["ls"])


@pytest.mark.asyncio
async def test_execute_tool_returns_tool_result(
    executor: SandboxExecutor, mock_docker: MagicMock
) -> None:
    """execute_tool maps ExecResult → ToolResult correctly."""
    fake_exec = _make_exec_mock(stdout_data=b"nmap output", exit_code=0)
    fake_container = MagicMock()
    fake_container.exec = AsyncMock(return_value=fake_exec)
    mock_docker.containers.container = MagicMock(return_value=fake_container)

    tool_result = await executor.execute_tool("cid123def456", "nmap", ["nmap", "-sV", "10.10.10.1"])
    assert tool_result.tool_name == "nmap"
    assert "nmap output" in tool_result.stdout


def test_exec_result_to_tool_result_mapping() -> None:
    """Static helper converts ExecResult fields correctly."""
    exec_result = ExecResult(
        exit_code=0,
        stdout="hello",
        stderr="",
        duration_seconds=1.2,
        command="echo hello",
    )
    tr = SandboxExecutor._exec_result_to_tool_result("mytool", exec_result)
    assert tr.tool_name == "mytool"
    assert tr.stdout == "hello"
    assert tr.duration_seconds == 1.2


def test_exec_result_to_tool_result_with_nonzero_exit() -> None:
    """Non-zero exit code is preserved in ToolResult."""
    exec_result = ExecResult(
        exit_code=127,
        stdout="",
        stderr="not found",
        duration_seconds=0.1,
        command="bad_cmd",
    )
    tr = SandboxExecutor._exec_result_to_tool_result("bad_cmd", exec_result)
    assert tr.exit_code == 127
