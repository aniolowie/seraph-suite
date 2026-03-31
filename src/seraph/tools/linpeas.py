"""LinPEAS privilege escalation enumeration tool wrapper.

Downloads and runs linpeas.sh locally (assumes already present at the
configured path) or fetches it from the PEASS-ng release URL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_DEFAULT_LINPEAS_PATH = Path("/opt/linpeas/linpeas.sh")
_LINPEAS_URL = "https://github.com/carlospolop/PEASS-ng/releases/latest/download/linpeas.sh"


class LinpeasTool(BaseTool):
    """LinPEAS Linux privilege escalation enumerator.

    Runs linpeas.sh on the local machine (or against a remote target via ssh
    in future). Returns the full output for LLM analysis.
    """

    name = "linpeas"
    description = (
        "Linux privilege escalation enumerator. Scans for misconfigurations, "
        "SUID/SGID binaries, writable paths, cron jobs, and kernel exploits. "
        "Use after obtaining an initial shell."
    )
    phases = [Phase.PRIVESC]
    timeout = 300

    def __init__(self, script_path: Path = _DEFAULT_LINPEAS_PATH) -> None:
        self._script_path = script_path

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run linpeas.sh.

        Args:
            args: Supported keys:
                - ``fast``: If True, add ``-s`` (skip heavy checks) flag.
                - ``sections``: Comma-separated section keys to run (optional).
                - ``script_path``: Override the linpeas.sh path.
            target: Target host (used for logging only in local mode).
        """
        cmd = self._build_command(args)
        stdout, stderr, exit_code, duration = await self._run_command(cmd)
        return self._build_result(" ".join(cmd), stdout, stderr, exit_code, duration)

    def _build_command(self, args: dict[str, Any]) -> list[str]:
        script_path = Path(str(args.get("script_path", self._script_path)))
        if not script_path.exists():
            raise FileNotFoundError(
                f"linpeas.sh not found at {script_path}. "
                f"Download with: curl -Lo {script_path} {_LINPEAS_URL}"
            )

        cmd = ["bash", str(script_path)]

        if args.get("fast", False):
            cmd.append("-s")

        sections = str(args.get("sections", ""))
        if sections:
            sections = self._sanitize_arg(sections)
            cmd.extend(["-i", sections])

        return cmd

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "fast": {
                        "type": "boolean",
                        "description": "Skip slow checks (-s flag).",
                    },
                    "sections": {
                        "type": "string",
                        "description": "Specific section keys to run (optional).",
                    },
                },
                "required": [],
            },
        }
