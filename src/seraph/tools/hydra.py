"""Hydra password brute-force tool wrapper."""

from __future__ import annotations

import re
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_VALID_SERVICE = frozenset(
    {
        "ftp",
        "ssh",
        "telnet",
        "smtp",
        "http-get",
        "http-post-form",
        "smb",
        "rdp",
        "vnc",
        "mysql",
        "mssql",
        "postgres",
    }
)
_PATH_RE = re.compile(r"^[a-zA-Z0-9_./ \-]+$")


class HydraTool(BaseTool):
    """Hydra network login brute-forcer.

    Tests username/password combinations against common network services.
    """

    name = "hydra"
    description = (
        "Network login brute-forcer. Tests credential lists against SSH, FTP, "
        "HTTP, SMB, RDP, and other services to find valid credentials."
    )
    phases = [Phase.EXPLOIT]
    timeout = 600

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run hydra.

        Args:
            args: Supported keys:
                - ``service``: Target service e.g. "ssh", "ftp" (required).
                - ``userlist``: Path to username list file (optional, uses ``username`` if absent).
                - ``username``: Single username to test (optional).
                - ``passlist``: Path to password list file (required).
                - ``port``: Service port override (optional).
                - ``tasks``: Number of parallel tasks (default 16).
                - ``http_form``: http-post-form parameters string (http-post-form mode only).
            target: Target host.
        """
        cmd = self._build_command(args, target)
        stdout, stderr, exit_code, duration = await self._run_command(cmd)
        return self._build_result(" ".join(cmd), stdout, stderr, exit_code, duration)

    def _build_command(self, args: dict[str, Any], target: TargetInfo) -> list[str]:
        service = str(args.get("service", ""))
        if service not in _VALID_SERVICE:
            raise ValueError(f"Unsupported service: {service!r}")

        passlist = str(args.get("passlist", ""))
        if not passlist or not _PATH_RE.match(passlist):
            raise ValueError(f"Invalid or missing passlist: {passlist!r}")

        tasks = int(args.get("tasks", 16))
        if tasks < 1 or tasks > 64:
            tasks = 16

        cmd = ["hydra", "-t", str(tasks)]

        userlist = str(args.get("userlist", ""))
        username = str(args.get("username", ""))
        if userlist:
            if not _PATH_RE.match(userlist):
                raise ValueError(f"Invalid userlist: {userlist!r}")
            cmd.extend(["-L", userlist])
        elif username:
            cmd.extend(["-l", self._sanitize_arg(username)])
        else:
            raise ValueError("Either 'userlist' or 'username' must be provided")

        cmd.extend(["-P", passlist])

        port = args.get("port")
        if port is not None:
            cmd.extend(["-s", str(int(port))])

        if service == "http-post-form":
            form_params = str(args.get("http_form", ""))
            if not form_params:
                raise ValueError("http_form required for http-post-form service")
            cmd.append(target.ip)
            cmd.append(f"{service}:{self._sanitize_arg(form_params)}")
        else:
            cmd.extend([target.ip, service])

        return cmd

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Target service (ssh/ftp/smb/...).",
                    },
                    "username": {"type": "string", "description": "Single username."},
                    "userlist": {"type": "string", "description": "Path to username list."},
                    "passlist": {"type": "string", "description": "Path to password list."},
                    "port": {"type": "integer", "description": "Service port override."},
                    "tasks": {"type": "integer", "description": "Parallel tasks (default 16)."},
                },
                "required": ["service", "passlist"],
            },
        }
