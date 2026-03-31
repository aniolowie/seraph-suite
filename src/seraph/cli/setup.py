"""``seraph setup`` — first-run wizard.

Handles: .env creation, API key prompt, Docker service startup,
and optional MITRE ATT&CK baseline ingestion.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import click

from seraph.cli.renderer import console, render_error, render_info, render_success, render_warning


@click.command(name="setup")
@click.option("--skip-docker", is_flag=True, help="Skip Docker service startup.")
@click.option("--skip-ingest", is_flag=True, help="Skip initial MITRE data ingestion.")
@click.option(
    "--local",
    is_flag=True,
    default=False,
    help="Configure a local Ollama model instead of Anthropic.",
)
def setup(skip_docker: bool, skip_ingest: bool, local: bool) -> None:
    """First-run setup: configure .env, start services, ingest baseline data."""
    console.print("\n[bold cyan]Seraph Setup[/bold cyan]\n")

    env_path = Path(".env")
    _ensure_env(env_path)

    if local:
        _configure_local_model(env_path)
    else:
        _ensure_api_key(env_path)

    services_running = False
    if not skip_docker:
        services_running = _start_services()
    else:
        render_info("Skipping Docker services.")

    if not skip_ingest and services_running:
        _ingest_mitre()
    elif not skip_ingest:
        render_warning(
            "Skipping MITRE ingest (no services)."
            " Run [bold]seraph ingest mitre --download[/bold] later."
        )

    console.print()
    render_success("Setup complete.")
    console.print(
        "\n  Run [bold cyan]seraph -t 10.10.10.X[/bold cyan] to start an engagement.\n"
        "  Run [bold cyan]seraph[/bold cyan] for the interactive REPL.\n"
    )


# ── Steps ─────────────────────────────────────────────────────────────────────


def _ensure_env(env_path: Path) -> None:
    if env_path.exists():
        render_success(".env already exists")
        return

    example = Path(".env.example")
    if example.exists():
        env_path.write_text(example.read_text())
    else:
        env_path.write_text(
            "ANTHROPIC_API_KEY=\n"
            "NEO4J_PASSWORD=seraph_secret\n"
            "QDRANT_URL=http://localhost:6333\n"
            "NEO4J_URI=bolt://localhost:7687\n"
            "REDIS_URL=redis://localhost:6379/0\n"
        )
    render_success(f"Created {env_path}")


def _configure_local_model(env_path: Path) -> None:
    """Prompt for local model settings and write them to .env."""
    console.print("\n[yellow]*[/yellow] Configuring local model (Ollama).")

    default_url = _read_env_value(env_path, "LOCAL_MODEL_URL") or "http://localhost:11434"
    url = console.input(f"  Ollama URL [{default_url}]: ").strip() or default_url

    default_model = _read_env_value(env_path, "LOCAL_MODEL_NAME") or "qwen2.5-coder:8b"
    model = console.input(f"  Model name [{default_model}]: ").strip() or default_model

    _write_env_value(env_path, "LOCAL_MODEL_ENABLED", "true")
    _write_env_value(env_path, "LOCAL_MODEL_URL", url)
    _write_env_value(env_path, "LOCAL_MODEL_NAME", model)
    render_success(f"Local model configured: [bold]{model}[/bold] at {url}")
    render_info(
        "Make sure Ollama is running and the model is pulled: "
        f"[bold]ollama pull {model}[/bold]"
    )


def _ensure_api_key(env_path: Path) -> None:
    import os

    live_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    file_key = _read_env_value(env_path, "ANTHROPIC_API_KEY")

    if live_key or (file_key and not file_key.startswith("sk-ant-...")):
        render_success("ANTHROPIC_API_KEY configured")
        return

    console.print("\n[yellow]![/yellow] ANTHROPIC_API_KEY is not set.")
    new_key = console.input("  Enter your Anthropic API key (sk-ant-...): ").strip()
    if new_key:
        _write_env_value(env_path, "ANTHROPIC_API_KEY", new_key)
        render_success("API key saved to .env")
    else:
        render_warning("Skipped. Set ANTHROPIC_API_KEY in .env before running.")


def _start_services() -> bool:
    if not _docker_ok():
        render_warning("Docker not found. Install Docker, then run [bold]make up[/bold].")
        return False

    console.print("\n[*] Starting Docker services (Qdrant, Neo4j, Redis)...")
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "qdrant", "neo4j", "redis"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        render_error(f"docker compose failed:\n{result.stderr[:400]}")
        return False

    render_success("Containers started")
    _wait_for_qdrant()
    return True


def _wait_for_qdrant(retries: int = 20) -> None:
    try:
        import httpx
    except ImportError:
        return

    console.print("  Waiting for Qdrant", end="")
    for _ in range(retries):
        try:
            r = httpx.get("http://localhost:6333/readyz", timeout=2.0)
            if r.status_code == 200:
                console.print(" [green]ready[/green]")
                return
        except Exception:
            pass
        console.print(".", end="")
        time.sleep(2)
    console.print(" [yellow]timed out — services may still be starting[/yellow]")


def _ingest_mitre() -> None:
    console.print("\n[*] Ingesting MITRE ATT&CK data (one-time, ~2 min)...")
    result = subprocess.run(
        [sys.executable, "-m", "seraph.cli.main", "ingest", "mitre", "--download"],
    )
    if result.returncode == 0:
        render_success("MITRE ATT&CK ingested into Neo4j + Qdrant")
    else:
        render_warning(
            "MITRE ingest failed. Run [bold]seraph ingest mitre --download[/bold] manually."
        )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _docker_ok() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _read_env_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _write_env_value(path: Path, key: str, value: str) -> None:
    content = path.read_text() if path.exists() else ""
    lines = content.splitlines()
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n")
