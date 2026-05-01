"""
ui.py – Console output helpers.

All Rich formatting is centralised here so the rest of the codebase
never imports Rich directly — only these helpers.
"""
from __future__ import annotations

import sys

try:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def print_header() -> None:
    if HAS_RICH:
        console.print(
            Panel.fit(
                "[bold cyan]MSK-PIPE Orchestrator[/bold cyan]\n"
                "Pre-flight checks and system setup",
                border_style="cyan",
            )
        )
    else:
        print("\n=== MSK-PIPE Orchestrator ===\nPre-flight checks and system setup")


def print_success(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[green]✓ {msg}[/green]")
    else:
        print(f"✓ {msg}")


def print_warning(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[yellow]! {msg}[/yellow]")
    else:
        print(f"! {msg}")


def print_error(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[red]✗ {msg}[/red]")
    else:
        print(f"✗ {msg}", file=sys.stderr)


def print_info(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[cyan]{msg}[/cyan]")
    else:
        print(msg)


def print_fatal(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[bold red]❌ Pre-flight failed: {msg}[/bold red]")
    else:
        print(f"❌ Pre-flight failed: {msg}", file=sys.stderr)


def print_section(title: str) -> None:
    """Print a section separator panel."""
    if HAS_RICH:
        console.print(
            Panel.fit(f"[bold cyan]{title}[/bold cyan]", border_style="cyan")
        )
    else:
        print(f"\n--- {title} ---")


from subprocess import CompletedProcess


def print_subprocess_error(
    proc: CompletedProcess | None = None,
    stderr: str = "",
    stdout: str = "",
    returncode: int | None = None,
) -> None:
    """Print subprocess diagnostics.

    Accepts either a CompletedProcess instance as the first argument (recommended),
    or the legacy (stderr, stdout, returncode) parameters.
    """
    parts: list[str] = []

    if proc is not None:
        # Print the invoked command when available
        try:
            parts.append(f"Command: {' '.join(proc.args) if isinstance(proc.args, (list, tuple)) else proc.args}")
        except Exception:
            parts.append(f"Command: {proc.args}")
        parts.append(f"Exit code: {proc.returncode}")
        if proc.stdout:
            parts.append("STDOUT:\n" + proc.stdout)
        if proc.stderr:
            parts.append("STDERR:\n" + proc.stderr)
    else:
        # Backwards-compatible path
        if returncode is not None:
            parts.append(f"Exit code: {returncode}")
        if stdout:
            parts.append("STDOUT:\n" + stdout)
        if stderr:
            parts.append("STDERR:\n" + stderr)

    out = "\n\n".join(parts)

    if out:
        if HAS_RICH:
            console.print(f"[white]{out}[/white]")
        else:
            print(out, file=sys.stderr)


def print_step(msg: str) -> None:
    """Print an in-progress step message (cyan, no prefix)."""
    if HAS_RICH:
        console.print(f"[cyan]{msg}[/cyan]")
    else:
        print(msg)


def print_check(title: str) -> None:
    """Print a section-level check header (yellow)."""
    if HAS_RICH:
        console.print(f"\n[yellow]{title}...[/yellow]")
    else:
        print(f"\n{title}...")


def print_launch(msg: str) -> None:
    """Print a bold green launch banner."""
    if HAS_RICH:
        console.print(f"\n[bold green]🚀 {msg}[/bold green]")
    else:
        print(f"\n🚀 {msg}")


def print_interrupt(msg: str) -> None:
    """Print a bold yellow interrupt/abort message."""
    if HAS_RICH:
        console.print(f"\n[bold yellow]⛔ {msg}[/bold yellow]")
    else:
        print(f"\n⛔ {msg}", file=sys.stderr)