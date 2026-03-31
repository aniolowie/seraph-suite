"""Unit tests for tool wrappers (nmap, gobuster, sqlmap, metasploit, curl, hydra)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from seraph.agents.state import TargetInfo
from seraph.exceptions import ToolTimeoutError
from seraph.tools.curl import CurlTool
from seraph.tools.gobuster import GobusterTool
from seraph.tools.hydra import HydraTool
from seraph.tools.metasploit import MetasploitTool
from seraph.tools.nmap import NmapTool
from seraph.tools.sqlmap import SqlmapTool


def _target() -> TargetInfo:
    return TargetInfo(ip="10.10.10.3", hostname="lame", ports=[22, 80, 445])


# ── NmapTool ──────────────────────────────────────────────────────────────────


class TestNmapTool:
    def test_builds_command_with_defaults(self) -> None:
        tool = NmapTool()
        cmd = tool._build_command({}, _target())
        assert cmd[0] == "nmap"
        assert "-oX" in cmd
        assert "10.10.10.3" in cmd

    def test_builds_command_with_ports(self) -> None:
        tool = NmapTool()
        cmd = tool._build_command({"ports": "22,80,443", "flags": ["-sV"]}, _target())
        assert "-p" in cmd
        assert "22,80,443" in cmd
        assert "-sV" in cmd

    def test_rejects_invalid_ports(self) -> None:
        tool = NmapTool()
        with pytest.raises(ValueError, match="port"):
            tool._build_command({"ports": "80;ls"}, _target())

    def test_rejects_invalid_flag(self) -> None:
        tool = NmapTool()
        with pytest.raises(ValueError, match="flag"):
            tool._build_command({"flags": ["--script=evil;ls"]}, _target())

    @pytest.mark.asyncio
    async def test_timeout_raises_tool_timeout_error(self) -> None:
        tool = NmapTool()
        tool.timeout = 1
        with patch.object(tool, "_run_command", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = ToolTimeoutError("timed out")
            with pytest.raises(ToolTimeoutError):
                await tool.execute({}, _target())


# ── GobusterTool ──────────────────────────────────────────────────────────────


class TestGobusterTool:
    def test_builds_dir_command(self) -> None:
        tool = GobusterTool()
        cmd = tool._build_command({"mode": "dir", "url": "http://10.10.10.3"}, _target())
        assert "dir" in cmd
        assert "http://10.10.10.3" in cmd

    def test_rejects_invalid_mode(self) -> None:
        tool = GobusterTool()
        with pytest.raises(ValueError, match="mode"):
            tool._build_command({"mode": "hack"}, _target())

    def test_dns_mode_uses_domain(self) -> None:
        tool = GobusterTool()
        cmd = tool._build_command({"mode": "dns", "domain": "example.com"}, _target())
        assert "dns" in cmd
        assert "example.com" in cmd


# ── SqlmapTool ────────────────────────────────────────────────────────────────


class TestSqlmapTool:
    def test_builds_command_with_url(self) -> None:
        tool = SqlmapTool()
        cmd = tool._build_command({"url": "http://10.10.10.3/?id=1"}, _target())
        assert "sqlmap" in cmd
        assert "--batch" in cmd
        assert "http://10.10.10.3/?id=1" in cmd

    def test_rejects_invalid_url(self) -> None:
        tool = SqlmapTool()
        with pytest.raises(ValueError, match="URL"):
            tool._build_command({"url": "ftp://evil"}, _target())

    def test_adds_dump_flag(self) -> None:
        tool = SqlmapTool()
        cmd = tool._build_command({"url": "http://10.10.10.3/", "dump": True}, _target())
        assert "--dump" in cmd


# ── CurlTool ──────────────────────────────────────────────────────────────────


class TestCurlTool:
    def test_builds_get_command(self) -> None:
        tool = CurlTool()
        cmd = tool._build_command({"url": "http://10.10.10.3/"}, _target())
        assert "curl" in cmd
        assert "http://10.10.10.3/" in cmd
        assert "-X" in cmd
        assert "GET" in cmd

    def test_post_with_data(self) -> None:
        tool = CurlTool()
        cmd = tool._build_command(
            {"url": "http://10.10.10.3/login", "method": "POST", "data": "user=admin"},
            _target(),
        )
        assert "POST" in cmd
        assert "--data-raw" in cmd

    def test_rejects_invalid_url(self) -> None:
        tool = CurlTool()
        with pytest.raises(ValueError, match="URL"):
            tool._build_command({"url": "not-a-url"}, _target())

    def test_rejects_invalid_method(self) -> None:
        tool = CurlTool()
        with pytest.raises(ValueError, match="method"):
            tool._build_command({"url": "http://target/", "method": "HACK"}, _target())


# ── HydraTool ─────────────────────────────────────────────────────────────────


class TestHydraTool:
    def test_builds_ssh_command(self) -> None:
        tool = HydraTool()
        cmd = tool._build_command(
            {"service": "ssh", "username": "admin", "passlist": "/usr/share/wordlists/rockyou.txt"},
            _target(),
        )
        assert "hydra" in cmd
        assert "ssh" in cmd
        assert "-l" in cmd
        assert "admin" in cmd

    def test_rejects_unknown_service(self) -> None:
        tool = HydraTool()
        with pytest.raises(ValueError, match="service"):
            tool._build_command(
                {"service": "telnet2", "username": "a", "passlist": "/tmp/p.txt"},
                _target(),
            )

    def test_raises_without_username_or_userlist(self) -> None:
        tool = HydraTool()
        with pytest.raises(ValueError, match="username"):
            tool._build_command(
                {"service": "ftp", "passlist": "/tmp/p.txt"},
                _target(),
            )


# ── MetasploitTool ────────────────────────────────────────────────────────────


class TestMetasploitTool:
    def test_rejects_invalid_module(self) -> None:
        tool = MetasploitTool()
        with pytest.raises(ValueError, match="module"):
            tool._build_command({"module": "evil;rm -rf /"}, _target())

    def test_builds_rc_script(self) -> None:
        tool = MetasploitTool()
        with patch("tempfile.NamedTemporaryFile") as mock_tmpfile:
            mock_file = mock_tmpfile.return_value.__enter__.return_value
            mock_file.name = "/tmp/test.rc"
            cmd, _rc_path = tool._build_command(
                {
                    "module": "exploit/unix/ftp/vsftpd_234_backdoor",
                    "options": {"LPORT": "4444"},
                },
                _target(),
            )
        assert "msfconsole" in cmd
        assert "-r" in cmd

    def test_rejects_invalid_option_key(self) -> None:
        tool = MetasploitTool()
        with pytest.raises(ValueError, match="option key"):
            tool._build_command(
                {"module": "exploit/test", "options": {"bad-key!": "value"}},
                _target(),
            )
