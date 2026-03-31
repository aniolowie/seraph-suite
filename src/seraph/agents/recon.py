"""Recon sub-agent — network discovery and service enumeration.

Uses nmap and curl to map the target's attack surface.  Produces ``Finding``
objects for each discovered service and updates ``EngagementState.target``
with discovered ports, services, and OS details.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import structlog

from seraph.agents.base_agent import BaseAgent
from seraph.agents.state import (
    EngagementState,
    Finding,
    FindingSeverity,
    Phase,
    TargetInfo,
)

log = structlog.get_logger(__name__)

_PORT_RE = re.compile(r"(\d+)/(\w+)\s+open\s+(\S*)\s*(.*)")


class ReconAgent(BaseAgent):
    """Recon sub-agent that enumerates the target's network attack surface.

    Runs an nmap scan, optionally probes HTTP services with curl, and
    produces findings for every discovered open port.
    """

    AGENT_NAME = "recon"

    async def run(self, state: EngagementState) -> EngagementState:
        """Execute reconnaissance against the target.

        1. Retrieve KB context for the target.
        2. Run nmap to discover open ports and services.
        3. Probe HTTP services with curl for technology hints.
        4. Parse results into Finding objects.
        5. Return updated state.

        Args:
            state: Current engagement state.

        Returns:
            Updated state with target info and findings populated.
        """
        state = state.model_copy(update={"current_agent": self.AGENT_NAME})
        state = await self._retrieve_context(state)

        system_prompt = self._render_prompt(
            "recon.jinja2",
            target=state.target,
            kb_context=state.kb_context,
        )

        tools = await self._select_tools(
            "network port scanning and service enumeration",
            phase=Phase.RECON,
            top_k=5,
        )

        state = self._add_message(
            state,
            "user",
            f"Perform reconnaissance on target {state.target.ip}. "
            "Start with an nmap scan, then probe interesting services.",
        )

        tool_call_count = 0
        new_findings: list[Finding] = []
        seen_finding_ids: set[str] = set()
        updated_target = state.target

        while tool_call_count < self._max_tool_calls:
            text, tool_calls, raw_content = await self._call_llm(state, system_prompt, tools)

            # Store the full assistant content (text + tool_use blocks) so the
            # conversation stays valid for the Anthropic API.
            if raw_content:
                state = self._add_message(state, "assistant", raw_content)

            # Surface LLM reasoning to the user.
            if text:
                await self._emit("llm_response", {"text": text})

            if not tool_calls:
                break

            tool_results: list[dict[str, Any]] = []
            for call in tool_calls:
                tool_call_count += 1
                result = await self._execute_tool(call["name"], call["input"], state.target)
                state = state.model_copy(update={"tool_outputs": [*state.tool_outputs, result]})

                if call["name"] == "nmap":
                    for f in _parse_nmap_findings(result.stdout, state.target):
                        if f.id not in seen_finding_ids:
                            new_findings.append(f)
                            seen_finding_ids.add(f.id)
                    updated_target = _update_target_from_nmap(result.stdout, updated_target)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call["id"],
                        "content": f"exit_code={result.exit_code}\n{result.stdout[:2000]}",
                    }
                )

            # Send all tool results as a list — NOT a JSON string.
            state = self._add_message(state, "user", tool_results)

        state = state.model_copy(
            update={
                "findings": [*state.findings, *new_findings],
                "target": updated_target,
            }
        )
        state = self._append_history(
            state,
            action="recon_complete",
            input_data={"target": state.target.ip},
            output=f"Discovered {len(new_findings)} services, {len(updated_target.ports)} ports",
        )

        log.info(
            "recon_agent.complete",
            target=state.target.ip,
            findings=len(new_findings),
            ports=len(updated_target.ports),
        )
        return state


# ── Parsing helpers ───────────────────────────────────────────────────────────


def _parse_nmap_findings(xml_output: str, target: TargetInfo) -> list[Finding]:
    """Extract open port findings from nmap XML output."""
    findings: list[Finding] = []
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError:
        return findings

    for host in root.findall("host"):
        for port_el in host.findall(".//port"):
            state_el = port_el.find("state")
            if state_el is None or state_el.get("state") != "open":
                continue

            portid = port_el.get("portid", "?")
            proto = port_el.get("protocol", "tcp")
            svc_el = port_el.find("service")
            svc_name = svc_el.get("name", "unknown") if svc_el is not None else "unknown"
            product = svc_el.get("product", "") if svc_el is not None else ""
            version = svc_el.get("version", "") if svc_el is not None else ""
            description = f"{svc_name}"
            if product:
                description += f" ({product} {version})".rstrip()

            findings.append(
                Finding(
                    id=f"recon-{target.ip}-{portid}",
                    title=f"{svc_name.upper()} on port {portid}/{proto}",
                    description=description,
                    severity=FindingSeverity.INFO,
                    phase=Phase.RECON,
                    mitre_techniques=["T1046"],
                )
            )
    return findings


def _update_target_from_nmap(xml_output: str, target: TargetInfo) -> TargetInfo:
    """Update TargetInfo with ports and OS discovered by nmap."""
    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError:
        return target

    ports: list[int] = []
    os_str = ""
    for host in root.findall("host"):
        for port_el in host.findall(".//port"):
            state_el = port_el.find("state")
            if state_el is not None and state_el.get("state") == "open":
                try:
                    ports.append(int(port_el.get("portid", "0")))
                except ValueError:
                    pass

        os_str = ""
        for osmatch in host.findall(".//osmatch"):
            os_str = osmatch.get("name", "")
            if os_str:
                break

    merged_ports = sorted(set(target.ports + ports))
    return TargetInfo(
        ip=target.ip,
        hostname=target.hostname,
        os=os_str or target.os,
        ports=merged_ports,
    )
