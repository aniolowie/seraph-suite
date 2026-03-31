"""Live HTB integration benchmarks.

These tests require:
  1. An active HackTheBox VPN connection (tun0 interface).
  2. Real flag hashes populated in machines.yaml.
  3. A valid ANTHROPIC_API_KEY in the environment.

Run with::

    make bench
    # or
    pytest tests/benchmarks/test_htb_live.py -v -m htb

Tests are skipped automatically when the VPN interface is absent or
flag values are placeholder strings.
"""

from __future__ import annotations

import os
import socket

import pytest

pytestmark = [pytest.mark.htb, pytest.mark.integration]


def _vpn_available() -> bool:
    """True if the tun0 VPN interface is up."""
    try:
        # socket.getaddrinfo will resolve tun0 address if interface exists.
        from seraph.config import settings

        iface = getattr(settings, "htb_vpn_interface", "tun0")
        return bool(iface) and os.path.exists(f"/sys/class/net/{iface}")
    except Exception:
        return False


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


skip_no_vpn = pytest.mark.skipif(
    not _vpn_available(),
    reason="HTB VPN interface not active",
)
skip_no_key = pytest.mark.skipif(
    not _has_api_key(),
    reason="ANTHROPIC_API_KEY not set",
)


@skip_no_vpn
@skip_no_key
@pytest.mark.asyncio
async def test_benchmark_lame(htb_machines: list[dict]) -> None:
    """Run Seraph against the Lame machine and verify it captures at least one flag."""
    from pathlib import Path

    from seraph.benchmarks.loader import MachineLoader
    from seraph.benchmarks.models import SolveOutcome
    from seraph.benchmarks.runner import BenchmarkRunner

    loader = MachineLoader(Path("tests/benchmarks/machines.yaml"))
    spec = loader.load_by_name("Lame")

    if not spec.has_real_flags:
        pytest.skip("Lame flags are placeholders — add real hashes to run this test")

    runner = BenchmarkRunner(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout_seconds=3600,
    )
    result = await runner.run_machine(spec)
    assert result.outcome in (SolveOutcome.SOLVED, SolveOutcome.PARTIAL), (
        f"Expected at least partial solve, got {result.outcome}: {result.error}"
    )


@skip_no_vpn
@skip_no_key
@pytest.mark.asyncio
async def test_benchmark_easy_batch(htb_machines: list[dict]) -> None:
    """Run all Easy machines and assert at least 50% solve rate."""
    from pathlib import Path

    from seraph.benchmarks.loader import MachineLoader
    from seraph.benchmarks.runner import BenchmarkRunner

    loader = MachineLoader(Path("tests/benchmarks/machines.yaml"))
    specs = loader.load_by_difficulty("Easy")

    if not any(s.has_real_flags for s in specs):
        pytest.skip("No Easy machines have real flag hashes")

    runner = BenchmarkRunner(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout_seconds=3600,
    )
    report = await runner.run_all(specs)
    assert report.solve_rate >= 0.5, (
        f"Expected ≥50% solve rate on Easy machines, got {report.solve_rate:.1%}"
    )


@skip_no_vpn
@skip_no_key
@pytest.mark.asyncio
async def test_benchmark_report_saved(tmp_path: "Path") -> None:
    """Benchmark one machine and verify the report is saved successfully."""
    from pathlib import Path

    from seraph.benchmarks.loader import MachineLoader
    from seraph.benchmarks.report import ReportGenerator
    from seraph.benchmarks.runner import BenchmarkRunner

    loader = MachineLoader(Path("tests/benchmarks/machines.yaml"))
    spec = loader.load_by_name("Lame")

    runner = BenchmarkRunner(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout_seconds=600,
    )
    report = await runner.run_all([spec])
    out = tmp_path / "bench_report.md"
    ReportGenerator().save(report, out)
    assert out.exists()
    assert spec.name in out.read_text()
