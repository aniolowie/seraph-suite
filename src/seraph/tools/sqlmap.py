"""SQLMap SQL injection testing tool wrapper."""

from __future__ import annotations

import re
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_VALID_LEVEL = frozenset({1, 2, 3, 4, 5})
_VALID_RISK = frozenset({1, 2, 3})
_URL_RE = re.compile(r"^https?://[^\s]+$")
_PARAM_RE = re.compile(r"^[a-zA-Z0-9_\-,]+$")
_DBMS_RE = re.compile(r"^[a-zA-Z0-9 ]+$")


class SqlmapTool(BaseTool):
    """SQLMap automated SQL injection detection and exploitation.

    Runs sqlmap in batch mode (no interactive prompts) and captures findings.
    """

    name = "sqlmap"
    description = (
        "Automated SQL injection scanner and exploiter. "
        "Tests web application parameters for SQL injection vulnerabilities."
    )
    phases = [Phase.EXPLOIT]
    timeout = 600

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run sqlmap against a URL.

        Args:
            args: Supported keys:
                - ``url``: Target URL with parameters (required).
                - ``params``: Comma-separated parameter names to test (optional).
                - ``level``: Testing level 1-5 (default 1).
                - ``risk``: Risk level 1-3 (default 1).
                - ``dbms``: Database backend hint e.g. "mysql" (optional).
                - ``dump``: If True, attempt to dump discovered databases.
                - ``data``: POST data string (optional).
            target: Target host.
        """
        cmd = self._build_command(args, target)
        stdout, stderr, exit_code, duration = await self._run_command(cmd)
        return self._build_result(" ".join(cmd), stdout, stderr, exit_code, duration)

    def _build_command(self, args: dict[str, Any], target: TargetInfo) -> list[str]:
        url = str(args.get("url", ""))
        if not url:
            url = f"http://{target.ip}"
        if not _URL_RE.match(url):
            raise ValueError(f"Invalid URL: {url!r}")

        cmd = ["sqlmap", "-u", url, "--batch", "--random-agent"]

        params = str(args.get("params", ""))
        if params:
            if not _PARAM_RE.match(params):
                raise ValueError(f"Invalid params: {params!r}")
            cmd.extend(["-p", params])

        level = int(args.get("level", 1))
        if level not in _VALID_LEVEL:
            level = 1
        cmd.extend(["--level", str(level)])

        risk = int(args.get("risk", 1))
        if risk not in _VALID_RISK:
            risk = 1
        cmd.extend(["--risk", str(risk)])

        dbms = str(args.get("dbms", ""))
        if dbms:
            if not _DBMS_RE.match(dbms):
                raise ValueError(f"Invalid dbms: {dbms!r}")
            cmd.extend(["--dbms", dbms])

        data = str(args.get("data", ""))
        if data:
            cmd.extend(["--data", self._sanitize_arg(data)])

        if args.get("dump", False):
            cmd.append("--dump")

        return cmd

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Target URL with parameters."},
                    "params": {
                        "type": "string",
                        "description": "Parameters to test, comma-separated.",
                    },
                    "level": {"type": "integer", "description": "Test level 1-5."},
                    "risk": {"type": "integer", "description": "Risk level 1-3."},
                    "dbms": {"type": "string", "description": "Database type hint."},
                    "dump": {"type": "boolean", "description": "Dump database contents."},
                },
                "required": ["url"],
            },
        }
