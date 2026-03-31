"""curl HTTP client tool wrapper."""

from __future__ import annotations

import re
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_VALID_METHOD = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"})
_URL_RE = re.compile(r"^https?://[^\s]+$")
_HEADER_RE = re.compile(r"^[a-zA-Z0-9\-]+: .+$")


class CurlTool(BaseTool):
    """curl HTTP client for manual web requests.

    Performs GET/POST/PUT/DELETE requests with custom headers, cookies,
    and data.  Useful for probing web endpoints and testing responses.
    """

    name = "curl"
    description = (
        "HTTP client for probing web endpoints. Sends GET/POST/PUT/DELETE requests "
        "with custom headers, cookies, and body data. Use to test web services."
    )
    phases = [Phase.RECON, Phase.ENUMERATE, Phase.EXPLOIT]
    timeout = 60

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Execute a curl request.

        Args:
            args: Supported keys:
                - ``url``: Target URL (required).
                - ``method``: HTTP method (default "GET").
                - ``headers``: Dict of header name → value.
                - ``data``: Request body string (for POST/PUT).
                - ``cookies``: Cookie string e.g. "session=abc123".
                - ``follow_redirects``: Follow Location headers (default True).
                - ``insecure``: Skip TLS verification (default True).
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

        method = str(args.get("method", "GET")).upper()
        if method not in _VALID_METHOD:
            raise ValueError(f"Invalid HTTP method: {method!r}")

        cmd = ["curl", "-s", "-i", "-X", method]

        if args.get("follow_redirects", True):
            cmd.append("-L")

        if args.get("insecure", True):
            cmd.append("-k")

        for name, value in args.get("headers", {}).items():
            header = f"{name}: {value}"
            if not _HEADER_RE.match(header):
                raise ValueError(f"Invalid header: {header!r}")
            cmd.extend(["-H", header])

        cookies = str(args.get("cookies", ""))
        if cookies:
            cmd.extend(["--cookie", self._sanitize_arg(cookies)])

        data = str(args.get("data", ""))
        if data:
            cmd.extend(["--data-raw", self._sanitize_arg(data)])

        cmd.append(url)
        return cmd

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Target URL."},
                    "method": {"type": "string", "description": "HTTP method (default GET)."},
                    "headers": {
                        "type": "object",
                        "description": "Request headers.",
                        "additionalProperties": {"type": "string"},
                    },
                    "data": {"type": "string", "description": "Request body."},
                    "cookies": {"type": "string", "description": "Cookie string."},
                },
                "required": ["url"],
            },
        }
