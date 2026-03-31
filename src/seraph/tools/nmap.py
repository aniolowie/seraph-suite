"""Nmap network scanner tool wrapper."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from seraph.agents.state import Phase, TargetInfo, ToolResult
from seraph.tools._base import BaseTool

_VALID_PORT_RE = re.compile(r"^\d{1,5}(-\d{1,5})?(,\d{1,5}(-\d{1,5})?)*$")
_VALID_FLAG_RE = re.compile(r"^-[a-zA-Z0-9]+$")


class NmapTool(BaseTool):
    """Nmap network scanner.

    Runs nmap against a target and returns structured port/service data
    parsed from XML output (``-oX -``).
    """

    name = "nmap"
    description = (
        "Network port scanner. Discovers open TCP/UDP ports, service versions, "
        "OS fingerprinting, and runs NSE scripts. Use for recon and service enumeration."
    )
    phases = [Phase.RECON, Phase.ENUMERATE]
    timeout = 600

    async def execute(self, args: dict[str, Any], target: TargetInfo) -> ToolResult:
        """Run nmap against the target.

        Args:
            args: Supported keys:
                - ``ports``: Port spec string e.g. "22,80,443" or "1-1000" (optional).
                - ``flags``: List of nmap flags e.g. ["-sV", "-O"] (optional).
                - ``scripts``: Comma-separated NSE scripts e.g. "vuln,auth" (optional).
                - ``timing``: Timing template 0-5 (default 4).
            target: Target host.

        Returns:
            ToolResult with parsed XML in stdout.
        """
        cmd = self._build_command(args, target)
        stdout, stderr, exit_code, duration = await self._run_command(cmd)
        result = self._build_result(" ".join(cmd), stdout, stderr, exit_code, duration)
        result = self._annotate_with_parsed(result, stdout)
        return result

    def _build_command(self, args: dict[str, Any], target: TargetInfo) -> list[str]:
        cmd = ["nmap", "-oX", "-"]

        timing = int(args.get("timing", 4))
        if timing < 0 or timing > 5:
            timing = 4
        cmd.append(f"-T{timing}")

        ports = args.get("ports", "")
        if ports:
            ports = str(ports)
            if not _VALID_PORT_RE.match(ports):
                raise ValueError(f"Invalid port specification: {ports!r}")
            cmd.extend(["-p", ports])
        else:
            cmd.append("--top-ports")
            cmd.append("1000")

        for flag in args.get("flags", []):
            flag = str(flag)
            if not _VALID_FLAG_RE.match(flag):
                raise ValueError(f"Invalid nmap flag: {flag!r}")
            cmd.append(flag)

        scripts = args.get("scripts", "")
        if scripts:
            scripts = self._sanitize_arg(str(scripts))
            cmd.extend(["--script", scripts])

        cmd.append(self._sanitize_arg(target.ip))
        return cmd

    def _annotate_with_parsed(self, result: ToolResult, xml_output: str) -> ToolResult:
        """Parse XML and attach a human-readable summary to stderr."""
        try:
            root = ET.fromstring(xml_output)
        except ET.ParseError:
            return result

        lines: list[str] = []
        for host in root.findall("host"):
            for port in host.findall(".//port"):
                portid = port.get("portid", "?")
                proto = port.get("protocol", "tcp")
                state_el = port.find("state")
                state = state_el.get("state", "?") if state_el is not None else "?"
                svc_el = port.find("service")
                svc = ""
                if svc_el is not None:
                    svc = svc_el.get("name", "")
                    product = svc_el.get("product", "")
                    version = svc_el.get("version", "")
                    if product:
                        svc = f"{svc} ({product} {version})".strip()
                lines.append(f"{portid}/{proto}  {state}  {svc}")

        summary = "\n".join(lines)
        return ToolResult(
            tool_name=result.tool_name,
            command=result.command,
            stdout=result.stdout,
            stderr=summary or result.stderr,
            exit_code=result.exit_code,
            duration_seconds=result.duration_seconds,
        )

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "ports": {
                        "type": "string",
                        "description": "Port spec: '22,80,443' or '1-1000'. Default: top 1000.",
                    },
                    "flags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Short nmap flags only, e.g. ['-sV', '-sC', '-A']. "
                            "Each must start with a single dash followed by letters/digits. "
                            "Do NOT pass '--top-ports' (handled internally) or '-O' (requires root)."
                        ),
                    },
                    "scripts": {
                        "type": "string",
                        "description": "NSE script categories e.g. 'vuln,auth'.",
                    },
                    "timing": {
                        "type": "integer",
                        "description": "Timing template 0-5 (default 4).",
                    },
                },
                "required": [],
            },
        }
