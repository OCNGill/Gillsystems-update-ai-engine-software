"""
cli.py — Rich terminal UI for GASU.

Provides colored output, progress bars, dry-run warnings, step logs,
and a final summary table.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Generator, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Custom theme
# ---------------------------------------------------------------------------

_THEME = Theme(
    {
        "info": "bright_cyan",
        "success": "bold bright_green",
        "warning": "bold yellow",
        "error": "bold red",
        "dry_run": "italic yellow",
        "header": "bold bright_blue",
        "step": "dim white",
        "version_old": "red",
        "version_new": "green",
    }
)

console = Console(theme=_THEME, highlight=False)
err_console = Console(theme=_THEME, highlight=False, stderr=True)


# ---------------------------------------------------------------------------
# Banner & header
# ---------------------------------------------------------------------------


def print_banner(dry_run: bool = False) -> None:
    title = "Gillsystems AI Stack Updater (GASU)"
    subtitle = "ROCm/HIP + llama.cpp — AMD Consumer GPU Edition"
    if dry_run:
        subtitle += "   [dry_run]◀ DRY-RUN MODE — no changes will be made ▶[/dry_run]"
    console.print(
        Panel(
            f"[header]{title}[/header]\n{subtitle}",
            border_style="bright_blue",
            padding=(0, 2),
        )
    )


def print_phase(phase: str) -> None:
    console.print(f"\n[header]━━━ {phase.upper()} ━━━[/header]")


def print_step(msg: str) -> None:
    console.print(f"  [step]▸ {msg}[/step]")


def print_info(msg: str) -> None:
    console.print(f"[info]ℹ  {msg}[/info]")


def print_success(msg: str) -> None:
    console.print(f"[success]✔  {msg}[/success]")


def print_warning(msg: str) -> None:
    console.print(f"[warning]⚠  {msg}[/warning]")


def print_error(msg: str) -> None:
    err_console.print(f"[error]✘  {msg}[/error]")


def print_dry_run(msg: str) -> None:
    console.print(f"[dry_run]  [DRY-RUN] {msg}[/dry_run]")


# ---------------------------------------------------------------------------
# Version summary table
# ---------------------------------------------------------------------------


def print_version_table(
    rows: List[Tuple[str, Optional[str], Optional[str], bool]]
) -> None:
    """
    Print a version comparison table.

    Args:
        rows: List of (component, installed, latest, needs_update) tuples.
    """
    table = Table(title="Version Status", border_style="bright_blue", expand=False)
    table.add_column("Component", style="bright_white", no_wrap=True)
    table.add_column("Installed", no_wrap=True)
    table.add_column("Latest", no_wrap=True)
    table.add_column("Status", no_wrap=True)

    for component, installed, latest, needs_update in rows:
        installed_str = installed or "[dim]not installed[/dim]"
        latest_str = latest or "[dim]unknown[/dim]"
        if needs_update:
            status = Text("UPDATE AVAILABLE", style="bold yellow")
            installed_styled = Text(installed_str, style="version_old")
        else:
            status = Text("current", style="success")
            installed_styled = Text(installed_str, style="success")

        table.add_row(component, installed_styled, latest_str, status)

    console.print(table)


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------


@contextmanager
def task_progress(description: str) -> Generator[None, None, None]:
    """Context manager that shows a spinner while a task runs."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task: TaskID = progress.add_task(description, total=None)
        try:
            yield
            progress.update(task, completed=1, total=1)
        except Exception:
            progress.stop()
            raise


# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------


def confirm(prompt: str, default: bool = False, auto_yes: bool = False) -> bool:
    """
    Ask the user for confirmation.

    Returns True if confirmed, False otherwise.
    Pass auto_yes=True to skip the prompt (--yes flag).
    """
    if auto_yes:
        print_info(f"{prompt} [auto-confirmed]")
        return True

    choices = "[Y/n]" if default else "[y/N]"
    console.print(f"[warning]{prompt} {choices}[/warning] ", end="")
    try:
        answer = input().strip().lower()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False

    if not answer:
        return default
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Reboot countdown
# ---------------------------------------------------------------------------


def reboot_countdown(seconds: int, auto_reboot: bool = True) -> bool:
    """
    Display a countdown before reboot. Returns True if user did not cancel.

    Args:
        seconds: Countdown duration.
        auto_reboot: If False, just warn and return False (manual reboot).

    Returns:
        True if reboot should proceed, False if cancelled or manual mode.
    """
    if not auto_reboot:
        print_warning(
            "System reboot is required to complete driver installation.\n"
            "  Please reboot manually and re-run the updater to continue."
        )
        return False

    import time
    console.print(
        f"\n[error]SYSTEM REBOOT REQUIRED[/error] — "
        f"rebooting in [bold]{seconds}[/bold] seconds. Press Ctrl+C to cancel.\n"
    )

    with Progress(
        TextColumn("[warning]Rebooting in {task.fields[remaining]}s — press Ctrl+C to cancel[/warning]"),
        BarColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("countdown", total=seconds, remaining=seconds)
        try:
            for i in range(seconds, 0, -1):
                progress.update(task, advance=1, remaining=i - 1)
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[success]Reboot cancelled by user.[/success]")
            console.print(
                "Re-run the updater after manually rebooting to continue the update."
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------


def print_summary(
    updates_applied: List[Tuple[str, str, str]],  # (component, old, new)
    dry_run: bool = False,
) -> None:
    """Print end-of-run summary."""
    print_phase("Summary")

    if not updates_applied:
        print_success("All components are already up to date. Nothing to do.")
        return

    table = Table(
        title="Updates Applied" + (" (DRY-RUN)" if dry_run else ""),
        border_style="green" if not dry_run else "yellow",
        expand=False,
    )
    table.add_column("Component", style="bright_white")
    table.add_column("Before", style="version_old")
    table.add_column("After", style="version_new")

    for component, old, new in updates_applied:
        table.add_row(component, old or "—", new or "—")

    console.print(table)

    if dry_run:
        print_dry_run("No changes were made. Remove --dry-run to execute.")
    else:
        print_success("All updates complete! Run `rocminfo` and `llama-cli --version` to verify.")
