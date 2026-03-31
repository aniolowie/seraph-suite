"""Abstract base class for all Seraph tool wrappers.

Every tool subclass must implement ``execute()`` and define ``name``,
``description``, ``phases``, and ``timeout``.  Shared subprocess execution,
timeout enforcement, and ``ToolResult`` construction live here.

Usage::

    class NmapTool(BaseTool):
        name = "nmap"
        description = "Network scanner ..."
        phases = [Phase.RECON]
        timeout = 600

        async def execute(self, args, target):
            cmd = self._build_command(args, target)
            stdout, stderr, code, duration = await self._run_command(cmd)
            return self._build_result(" ".join(cmd), stdout, stderr, code, duration)
"""

from __future__ import annotations

import asyncio
import shlex
import time
from abc import ABC, abstractmethod
from typing import Any

import structlog

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.exceptions import ToolTimeoutError

log = structlog.get_logger(__name__)

# Characters that must never appear in tool arguments passed to subprocess.
_SHELL_METACHARACTERS = frozenset(";|&`$(){}[]<>\\\n\r\t")


class BaseTool(ABC):
    """Abstract base for all pentesting tool wrappers.

    Subclasses define class-level attributes and implement ``execute()``.
    """

    #: Unique tool name, must match the key in ``configs/tools.yaml``.
    name: str
    #: Human-readable description used for RAG-based tool selection.
    description: str
    #: Engagement phases this tool is relevant for.
    phases: list[Phase]
    #: Default execution timeout in seconds.
    timeout: int = 300

    @abstractmethod
    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run the tool and return a ``ToolResult``.

        Args:
            args: Tool-specific arguments validated by the subclass.
            target: Target host information.

        Returns:
            Populated ``ToolResult`` instance.

        Raises:
            ToolTimeoutError: If execution exceeds ``self.timeout``.
            ToolExecutionError: On subprocess failure.
        """

    # ── Shared helpers ────────────────────────────────────────────────────────

    async def _run_command(
        self,
        command: list[str],
        timeout: int | None = None,
    ) -> tuple[str, str, int, float]:
        """Execute a command and return (stdout, stderr, exit_code, duration_secs).

        Args:
            command: Command and arguments as a list (no shell expansion).
            timeout: Override the default tool timeout.

        Returns:
            Tuple of (stdout, stderr, exit_code, duration_seconds).

        Raises:
            ToolTimeoutError: If the process exceeds ``timeout``.
        """
        effective_timeout = timeout or self.timeout
        cmd_str = shlex.join(command)
        log.debug("tool.run", tool=self.name, command=cmd_str)

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
            duration = time.monotonic() - start
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            exit_code = proc.returncode or 0
            log.debug(
                "tool.finished",
                tool=self.name,
                exit_code=exit_code,
                duration=round(duration, 2),
            )
            return stdout, stderr, exit_code, duration
        except TimeoutError as exc:
            duration = time.monotonic() - start
            log.warning("tool.timeout", tool=self.name, timeout=effective_timeout)
            raise ToolTimeoutError(f"{self.name} timed out after {effective_timeout}s") from exc

    def _build_result(
        self,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration: float,
    ) -> ToolResult:
        """Construct a ``ToolResult`` from raw subprocess output."""
        return ToolResult(
            tool_name=self.name,
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_seconds=round(duration, 3),
        )

    @staticmethod
    def _sanitize_arg(value: str) -> str:
        """Reject strings containing shell metacharacters.

        Args:
            value: A string argument to validate.

        Returns:
            The original value if safe.

        Raises:
            ValueError: If the value contains shell metacharacters.
        """
        bad = _SHELL_METACHARACTERS & set(value)
        if bad:
            raise ValueError(f"Tool argument contains forbidden characters {bad!r}: {value!r}")
        return value

    def to_sandbox_command(
        self,
        args: dict[str, Any],
        target: TargetInfo,
    ) -> list[str]:
        """Return the command list to run this tool inside a sandbox container.

        Delegates to ``_build_command`` if the subclass defines it,
        otherwise raises ``NotImplementedError``.

        Args:
            args: Tool-specific arguments (same as passed to ``execute``).
            target: Target host information.

        Returns:
            Command and arguments as a list suitable for ``docker exec``.

        Raises:
            NotImplementedError: If the subclass does not implement ``_build_command``.
        """
        if hasattr(self, "_build_command"):
            return self._build_command(args, target)  # type: ignore[attr-defined]
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _build_command to support sandbox execution"
        )

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Return the Anthropic tool-use JSON schema for this tool.

        Subclasses may override to provide a richer ``input_schema``.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
