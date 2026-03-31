"""Metasploit Framework tool wrapper.

Executes msfconsole with a generated resource script.  Returns raw console
output for the agent to parse.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_MODULE_RE = re.compile(r"^[a-zA-Z0-9_/]+$")
_OPTION_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_OPTION_VAL_RE = re.compile(r"^[a-zA-Z0-9_.:/\-]+$")


class MetasploitTool(BaseTool):
    """Metasploit Framework exploit and post-exploitation runner.

    Generates a Metasploit resource script and runs it via ``msfconsole -x``.
    Suitable for exploit modules, auxiliary scanners, and post modules.
    """

    name = "metasploit"
    description = (
        "Metasploit Framework exploit and post-exploitation runner. "
        "Use to run exploit modules, auxiliary scanners, and post-exploitation "
        "modules against a target."
    )
    phases = [Phase.EXPLOIT, Phase.PRIVESC, Phase.POST]
    timeout = 900

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run a Metasploit module via msfconsole.

        Args:
            args: Supported keys:
                - ``module``: Module path e.g. "exploit/unix/ftp/vsftpd_234_backdoor" (required).
                - ``options``: Dict of module options e.g. {"LHOST": "10.10.14.1"} (optional).
                - ``payload``: Payload string e.g. "cmd/unix/interact" (optional).
                - ``extra_commands``: List of additional rc commands to append (optional).
            target: Target host.
        """
        cmd, rc_path = self._build_command(args, target)
        try:
            stdout, stderr, exit_code, duration = await self._run_command(cmd)
        finally:
            Path(rc_path).unlink(missing_ok=True)
        return self._build_result(" ".join(cmd), stdout, stderr, exit_code, duration)

    def _build_command(self, args: dict[str, Any], target: TargetInfo) -> tuple[list[str], str]:
        module = str(args.get("module", ""))
        if not module or not _MODULE_RE.match(module):
            raise ValueError(f"Invalid or missing module: {module!r}")

        options: dict[str, str] = {
            "RHOSTS": target.ip,
        }
        for k, v in args.get("options", {}).items():
            k, v = str(k), str(v)
            if not _OPTION_KEY_RE.match(k):
                raise ValueError(f"Invalid option key: {k!r}")
            if not _OPTION_VAL_RE.match(v):
                raise ValueError(f"Invalid option value: {v!r}")
            options[k] = v

        rc_lines = [f"use {module}"]
        for k, v in options.items():
            rc_lines.append(f"set {k} {v}")

        payload = str(args.get("payload", ""))
        if payload:
            if not _MODULE_RE.match(payload):
                raise ValueError(f"Invalid payload: {payload!r}")
            rc_lines.append(f"set PAYLOAD {payload}")

        for extra_cmd in args.get("extra_commands", []):
            rc_lines.append(self._sanitize_arg(str(extra_cmd)))

        rc_lines.extend(["run", "exit"])

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".rc", delete=False, prefix="seraph_msf_"
        ) as fh:
            fh.write("\n".join(rc_lines) + "\n")
            rc_path = fh.name

        cmd = ["msfconsole", "-q", "-r", rc_path]
        return cmd, rc_path

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": (
                            "Metasploit module path e.g. 'exploit/unix/ftp/vsftpd_234_backdoor'."
                        ),
                    },
                    "options": {
                        "type": "object",
                        "description": "Module options dict e.g. {'LHOST': '10.10.14.1'}.",
                        "additionalProperties": {"type": "string"},
                    },
                    "payload": {
                        "type": "string",
                        "description": "Payload to use e.g. 'cmd/unix/interact'.",
                    },
                },
                "required": ["module"],
            },
        }
