"""Rich terminal renderer — all visual output for the Seraph REPL."""

from __future__ import annotations

from collections import deque

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "tool": "dim cyan",
        "phase": "bold magenta",
        "sev.critical": "bold red",
        "sev.high": "red",
        "sev.medium": "yellow",
        "sev.low": "cyan",
        "sev.info": "dim white",
    }
)

console = Console(theme=_THEME, highlight=False)

# Circular buffer of tool outputs — keyed by index for `output N` command.
_MAX_STORED = 50
_output_store: deque[dict[str, str]] = deque(maxlen=_MAX_STORED)
_output_counter = 0

_BANNER = """\
  ███████╗███████╗██████╗  █████╗ ██████╗ ██╗  ██╗
  ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██║  ██║
  ███████╗█████╗  ██████╔╝███████║██████╔╝███████║
  ╚════██║██╔══╝  ██╔══██╗██╔══██║██╔═══╝ ██╔══██║
  ███████║███████╗██║  ██║██║  ██║██║     ██║  ██║
  ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝
"""

_HELP = """
  [bold]Commands:[/bold]
    [cyan]<target IP>[/cyan]       Start a new engagement
    [cyan]findings[/cyan]          Show all current findings
    [cyan]status[/cyan]            Show engagement status
    [cyan]output[/cyan]            Show last tool output
    [cyan]output <N>[/cyan]        Show tool output #N
    [cyan]outputs[/cyan]           List all stored tool outputs
    [cyan]clear[/cyan]             Clear current engagement
    [cyan]help[/cyan]              Show this message
    [cyan]quit[/cyan] / [cyan]exit[/cyan]       Exit Seraph

  [bold]Mid-engagement:[/bold]
    Type any instruction to steer the agent (e.g. "focus on port 445")

  [bold]Logs:[/bold]
    Full debug logs are written to [dim]~/.seraph/seraph.log[/dim]
    Run [cyan]seraph --verbose[/cyan] to stream them to the console
"""

_SEV_STYLE: dict[str, str] = {
    "critical": "sev.critical",
    "high": "sev.high",
    "medium": "sev.medium",
    "low": "sev.low",
    "info": "sev.info",
}


def render_banner() -> None:
    """Print the Seraph ASCII banner."""
    console.print(_BANNER, style="bold cyan")
    console.print(
        "  [dim]AI Pentest Agent Suite[/dim]  •  "
        "Type a target IP or [bold]help[/bold]\n"
    )


def render_help() -> None:
    """Print the help text."""
    console.print(_HELP)


def render_info(msg: str) -> None:
    console.print(f"[info][*][/info] {msg}")


def render_success(msg: str) -> None:
    console.print(f"[success][+][/success] {msg}")


def render_warning(msg: str) -> None:
    console.print(f"[warning][!][/warning] {msg}")


def render_error(msg: str) -> None:
    console.print(f"[error][✗][/error] {msg}")


def render_phase(phase: str) -> None:
    console.print(f"\n[phase]━━ Phase: {phase.upper()} ━━[/phase]\n")


def render_agent_start(agent: str, phase: str) -> None:
    console.print(f"[dim]  [{agent} / {phase}][/dim]")


def render_tool_start(name: str, args: dict) -> None:
    arg_str = " ".join(
        f"{k}={v}" for k, v in args.items() if v not in (None, "", [])
    )
    console.print(f"  [tool]▸ {name}[/tool] [dim]{arg_str}[/dim]")


def render_tool_end(
    name: str,
    exit_code: int,
    duration: float,
    stdout: str = "",
    stderr: str = "",
) -> None:
    """Render tool completion line and store output for later retrieval."""
    global _output_counter
    ok = "[success]✓[/success]" if exit_code == 0 else "[error]✗[/error]"

    combined = (stdout + "\n" + stderr).strip()
    if combined:
        _output_counter += 1
        idx = _output_counter
        _output_store.append({"idx": str(idx), "name": name, "output": combined})
        n_lines = combined.count("\n") + 1
        hint = f" [dim][#{idx} · {n_lines} lines — 'output {idx}' to view][/dim]"
    else:
        hint = ""

    console.print(f"  {ok} [dim]{name} ({duration:.1f}s)[/dim]{hint}")


def render_tool_output(idx: int | None = None) -> None:
    """Print stored tool output.  No idx = show the most recent."""
    if not _output_store:
        console.print("[dim]No tool output stored yet.[/dim]")
        return

    if idx is None:
        entry = _output_store[-1]
    else:
        entry = next((e for e in _output_store if e["idx"] == str(idx)), None)
        if entry is None:
            console.print(f"[error]No output stored for #{idx}.[/error]")
            return

    console.print(
        Panel(
            entry["output"],
            title=f"[tool]{entry['name']}[/tool] output [dim]#{entry['idx']}[/dim]",
            border_style="dim",
            expand=False,
        )
    )


def render_output_list() -> None:
    """Print a summary of all stored tool outputs."""
    if not _output_store:
        console.print("[dim]No tool output stored.[/dim]")
        return
    for entry in _output_store:
        n = entry["output"].count("\n") + 1
        console.print(f"  [dim]#{entry['idx']}[/dim]  [tool]{entry['name']}[/tool]  [dim]{n} lines[/dim]")


def render_finding(title: str, description: str, severity: str) -> None:
    style = _SEV_STYLE.get(severity.lower(), "sev.info")
    console.print(f"  [{style}][{severity.upper():8}][/{style}]  {title}")
    if description and description != title:
        console.print(f"             [dim]{description[:120]}[/dim]")


def render_findings_table(findings: list[dict]) -> None:
    if not findings:
        render_info("No findings yet.")
        return
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Severity", width=10)
    table.add_column("Phase", width=10)
    table.add_column("Title")
    for f in findings:
        sev = f.get("severity", "info")
        style = _SEV_STYLE.get(sev.lower(), "sev.info")
        table.add_row(
            f"[{style}]{sev.upper()}[/{style}]",
            f.get("phase", ""),
            f.get("title", ""),
        )
    console.print(table)


def render_status(target_ip: str, phase: str, n_findings: int, n_flags: int, iteration: int) -> None:
    console.print(f"  Target     [bold]{target_ip}[/bold]")
    console.print(f"  Phase      [bold]{phase}[/bold]")
    console.print(f"  Findings   [bold]{n_findings}[/bold]")
    console.print(f"  Flags      [bold]{n_flags}[/bold]")
    console.print(f"  Iteration  {iteration}")


def render_llm_text(text: str) -> None:
    if text.strip():
        console.print(Markdown(text.strip()))


def prompt_input(prompt: str = "") -> str:
    """Read a line from stdin with a styled prompt."""
    return console.input(f"\n[bold cyan]seraph[/bold cyan][dim]{' ' + prompt if prompt else ''}[/dim][bold cyan]>[/bold cyan] ")
