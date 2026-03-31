"""Gobuster directory/vhost/DNS enumeration tool wrapper."""

from __future__ import annotations

import re
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_VALID_MODE = frozenset({"dir", "vhost", "dns"})
_VALID_EXT_RE = re.compile(r"^[a-zA-Z0-9,]+$")


class GobusterTool(BaseTool):
    """Gobuster web content and vhost enumerator.

    Supports ``dir`` (directory bruteforce), ``vhost`` (virtual host discovery),
    and ``dns`` (subdomain enumeration) modes.
    """

    name = "gobuster"
    description = (
        "Web directory, virtual host, and DNS subdomain brute-forcer. "
        "Use to find hidden paths, subdomains, and admin panels."
    )
    phases = [Phase.ENUMERATE]
    timeout = 300

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run gobuster.

        Args:
            args: Supported keys:
                - ``mode``: "dir" | "vhost" | "dns" (default "dir").
                - ``url``: Target URL for dir/vhost modes (optional, built from target).
                - ``wordlist``: Path to wordlist file.
                - ``extensions``: File extensions e.g. "php,html,txt" (dir mode only).
                - ``threads``: Number of threads (default 20).
                - ``status_codes``: Comma-separated codes to show (default "200,204,301,302").
            target: Target host.
        """
        cmd = self._build_command(args, target)
        stdout, stderr, exit_code, duration = await self._run_command(cmd)
        return self._build_result(" ".join(cmd), stdout, stderr, exit_code, duration)

    def _build_command(self, args: dict[str, Any], target: TargetInfo) -> list[str]:
        mode = str(args.get("mode", "dir"))
        if mode not in _VALID_MODE:
            raise ValueError(f"Invalid gobuster mode: {mode!r}")

        default_wl = "/usr/share/wordlists/dirb/common.txt"
        wordlist = self._sanitize_arg(str(args.get("wordlist", default_wl)))
        threads = int(args.get("threads", 20))
        if threads < 1 or threads > 200:
            threads = 20

        cmd = ["gobuster", mode, "-w", wordlist, "-t", str(threads), "--no-error"]

        if mode in ("dir", "vhost"):
            url = args.get("url", "")
            if not url:
                port = 80
                if target.ports:
                    port = next(
                        (p for p in target.ports if p in (80, 443, 8080, 8443)),
                        target.ports[0],
                    )
                scheme = "https" if port in (443, 8443) else "http"
                url = f"{scheme}://{target.ip}:{port}"
            cmd.extend(["-u", self._sanitize_arg(str(url))])

            if mode == "dir":
                ext = str(args.get("extensions", ""))
                if ext:
                    if not _VALID_EXT_RE.match(ext):
                        raise ValueError(f"Invalid extensions: {ext!r}")
                    cmd.extend(["-x", ext])

                codes = str(args.get("status_codes", "200,204,301,302,307"))
                if not _VALID_EXT_RE.match(codes.replace(",", "")):
                    raise ValueError(f"Invalid status codes: {codes!r}")
                cmd.extend(["-s", codes])

        elif mode == "dns":
            domain = self._sanitize_arg(str(args.get("domain", target.hostname or target.ip)))
            cmd.extend(["-d", domain])

        return cmd

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["dir", "vhost", "dns"]},
                    "url": {"type": "string", "description": "Target URL (dir/vhost modes)."},
                    "wordlist": {"type": "string", "description": "Path to wordlist file."},
                    "extensions": {
                        "type": "string",
                        "description": "File extensions, comma-separated.",
                    },
                    "threads": {"type": "integer", "description": "Thread count (default 20)."},
                },
                "required": [],
            },
        }
