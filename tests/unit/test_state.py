"""Unit tests for EngagementState and related models."""

from __future__ import annotations

from seraph.agents.state import (
    EngagementState,
    Finding,
    FindingSeverity,
    Phase,
    TargetInfo,
)


class TestTargetInfo:
    def test_minimal_construction(self) -> None:
        t = TargetInfo(ip="10.10.10.3")
        assert t.ip == "10.10.10.3"
        assert t.hostname == ""
        assert t.ports == []

    def test_full_construction(self) -> None:
        t = TargetInfo(ip="10.10.10.3", hostname="lame.htb", os="Linux", ports=[22, 80, 445])
        assert t.ports == [22, 80, 445]


class TestFinding:
    def test_defaults(self) -> None:
        f = Finding(
            id="f-001",
            title="SQL Injection",
            description="Login form vulnerable",
            phase=Phase.EXPLOIT,
        )
        assert f.severity == FindingSeverity.INFO
        assert f.cve_ids == []
        assert f.mitre_techniques == []


class TestEngagementState:
    def test_initial_state(self) -> None:
        state = EngagementState(target=TargetInfo(ip="10.10.10.3"))
        assert state.phase == Phase.RECON
        assert state.findings == []
        assert state.flags == []
        assert state.error == ""

    def test_immutable_copy_update(self) -> None:
        state = EngagementState(target=TargetInfo(ip="10.10.10.3"))
        new_state = state.model_copy(update={"phase": Phase.EXPLOIT})
        assert state.phase == Phase.RECON  # original unchanged
        assert new_state.phase == Phase.EXPLOIT

    def test_add_finding(self) -> None:
        state = EngagementState(target=TargetInfo(ip="10.10.10.3"))
        finding = Finding(
            id="f-001", title="RCE", description="Remote code execution", phase=Phase.EXPLOIT
        )
        new_state = state.model_copy(update={"findings": [*state.findings, finding]})
        assert len(new_state.findings) == 1
        assert new_state.findings[0].id == "f-001"

    def test_capture_flag(self) -> None:
        state = EngagementState(target=TargetInfo(ip="10.10.10.3"))
        new_state = state.model_copy(update={"flags": ["user_flag_abc123"]})
        assert "user_flag_abc123" in new_state.flags
