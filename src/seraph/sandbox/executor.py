"""Sandbox command and tool execution via docker exec.

Runs arbitrary commands inside a running sandbox container and maps
results to ``ToolResult`` / ``ExecResult`` models.  Timeouts are
enforced with ``asyncio.wait_for``, raising ``CommandTimeoutError``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from seraph.agents.state import ToolResult
from seraph.exceptions import CommandTimeoutError, SandboxError
from seraph.sandbox.models import ExecResult

log = structlog.get_logger(__name__)

# Default timeout (seconds) when none is specified per-call.
_DEFAULT_EXEC_TIMEOUT = 60


class SandboxExecutor:
    """Executes commands inside a sandbox container via docker exec.

    Wraps aiodocker's exec API and converts raw output to typed result
    objects.  Can be injected into ``BaseAgent`` as the strategy for
    routing tool calls through the sandbox.

    Args:
        docker_client: An ``aiodocker.Docker`` instance.
    """

    def __init__(self, docker_client: object) -> None:
        self._docker = docker_client

    async def execute_command(
        self,
        container_id: str,
        command: list[str],
        timeout: int = _DEFAULT_EXEC_TIMEOUT,
        workdir: str = "/workspace",
    ) -> ExecResult:
        """Run a command inside a container and return the raw result.

        Args:
            container_id: Target container ID.
            command: Command + arguments as a list (no shell expansion).
            timeout: Maximum seconds to wait before raising ``CommandTimeoutError``.
            workdir: Working directory inside the container.

        Returns:
            ``ExecResult`` with stdout, stderr, exit_code, and timing.

        Raises:
            CommandTimeoutError: If execution exceeds ``timeout``.
            SandboxError: On unexpected aiodocker error.
        """
        cmd_str = " ".join(command)
        log.debug(
            "sandbox.executor.exec",
            container_id=container_id[:12],
            command=cmd_str,
            timeout=timeout,
        )
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_exec(container_id, command, workdir),
                timeout=float(timeout),
            )
            duration = time.monotonic() - start
            log.debug(
                "sandbox.executor.done",
                container_id=container_id[:12],
                exit_code=result[0],
                duration=round(duration, 2),
            )
            exit_code, stdout, stderr = result
            return ExecResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=round(duration, 3),
                timed_out=False,
                command=cmd_str,
            )
        except TimeoutError as exc:
            duration = time.monotonic() - start
            log.warning(
                "sandbox.executor.timeout",
                container_id=container_id[:12],
                command=cmd_str,
                timeout=timeout,
            )
            raise CommandTimeoutError(
                f"Command timed out after {timeout}s in container {container_id[:12]!r}: {cmd_str}"
            ) from exc
        except CommandTimeoutError:
            raise
        except Exception as exc:
            raise SandboxError(f"docker exec failed in {container_id[:12]!r}: {exc}") from exc

    async def execute_tool(
        self,
        container_id: str,
        tool_name: str,
        command: list[str],
        timeout: int = _DEFAULT_EXEC_TIMEOUT,
    ) -> ToolResult:
        """Run a tool command and map the output to a ``ToolResult``.

        Args:
            container_id: Target container ID.
            tool_name: Name of the tool (used to populate ``ToolResult.tool_name``).
            command: Full command + arguments as a list.
            timeout: Execution timeout in seconds.

        Returns:
            Populated ``ToolResult``.

        Raises:
            CommandTimeoutError: If execution exceeds ``timeout``.
            ToolExecutionError: If the tool exits non-zero.
            SandboxError: On unexpected Docker error.
        """
        exec_result = await self.execute_command(
            container_id=container_id,
            command=command,
            timeout=timeout,
        )
        return self._exec_result_to_tool_result(tool_name, exec_result)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run_exec(
        self,
        container_id: str,
        command: list[str],
        workdir: str,
    ) -> tuple[int, str, str]:
        """Low-level aiodocker exec invocation.

        Returns:
            (exit_code, stdout, stderr) tuple.
        """
        container = self._docker.containers.container(container_id)
        exec_instance = await container.exec(
            {
                "Cmd": command,
                "AttachStdout": True,
                "AttachStderr": True,
                "WorkingDir": workdir,
            }
        )
        async with exec_instance.start(detach=False) as stream:
            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []
            async for msg_type, data in stream:
                # msg_type 1 = stdout, 2 = stderr
                if msg_type == 1:
                    stdout_chunks.append(data)
                elif msg_type == 2:
                    stderr_chunks.append(data)

        inspect = await exec_instance.inspect()
        exit_code: int = inspect.get("ExitCode", -1)
        stdout = b"".join(stdout_chunks).decode(errors="replace")
        stderr = b"".join(stderr_chunks).decode(errors="replace")
        return exit_code, stdout, stderr

    @staticmethod
    def _exec_result_to_tool_result(
        tool_name: str,
        result: ExecResult,
        extra: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Convert an ``ExecResult`` to a ``ToolResult``.

        Args:
            tool_name: Logical tool name.
            result: Raw execution result.
            extra: Optional extra metadata to include in the finding summary.

        Returns:
            Populated ``ToolResult``.
        """
        return ToolResult(
            tool_name=tool_name,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_seconds=result.duration_seconds,
        )
