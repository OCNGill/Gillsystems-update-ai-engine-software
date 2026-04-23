"""
privilege.py — Privilege elevation for GASU.

Linux:  checks os.geteuid() == 0, re-executes with sudo if needed.
Windows: checks IsUserAnAdmin(), re-launches with ShellExecute runas if needed.
"""
from __future__ import annotations

import os
import sys
import subprocess
import logging
from typing import NoReturn

logger = logging.getLogger(__name__)


class PrivilegeError(RuntimeError):
    """Raised when privilege elevation is not possible."""


def is_admin() -> bool:
    """Return True if the current process is running with admin/root privileges."""
    if sys.platform == "win32":
        return _is_admin_windows()
    return os.geteuid() == 0  # type: ignore[attr-defined]


def ensure_admin() -> None:
    """
    Verify admin/root status. If not elevated, re-launch with elevation and exit.
    On Windows this opens a UAC prompt. On Linux it re-executes via sudo.
    """
    if is_admin():
        logger.debug("Privilege check passed — running as admin/root.")
        return

    logger.info("Not running with elevated privileges. Requesting elevation...")

    if sys.platform == "win32":
        _elevate_windows()
    else:
        _elevate_linux()


# ---------------------------------------------------------------------------
# Windows elevation
# ---------------------------------------------------------------------------


def _is_admin_windows() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate_windows() -> NoReturn:
    """Re-launch with 'runas' via ShellExecuteW (triggers UAC prompt)."""
    import ctypes

    logger.info("Requesting UAC elevation via ShellExecuteW runas...")

    script = os.path.abspath(sys.argv[0])
    params = " ".join(f'"{a}"' for a in sys.argv[1:])

    # ShellExecuteW returns > 32 on success
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,       # hwnd
        "runas",    # operation
        sys.executable,  # file
        f'"{script}" {params}',  # parameters
        None,       # directory
        1,          # SW_SHOWNORMAL
    )

    if ret <= 32:
        raise PrivilegeError(
            f"UAC elevation failed (ShellExecuteW returned {ret}). "
            "Please run as Administrator manually."
        )

    logger.info("Elevated process launched. Exiting current (unprivileged) process.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Linux elevation
# ---------------------------------------------------------------------------


def _elevate_linux() -> NoReturn:
    """Re-execute the current script via sudo."""
    if not _sudo_available():
        raise PrivilegeError(
            "sudo is not available and process is not root. "
            "Run with: sudo python3 src/main.py"
        )

    logger.info("Re-executing via sudo...")

    cmd = ["sudo", sys.executable] + sys.argv
    logger.debug("Elevator command: %s", " ".join(cmd))

    # Replace the current process — audit log is written before this
    os.execvp("sudo", cmd)  # type: ignore[attr-defined]
    # execvp never returns on success
    raise PrivilegeError("os.execvp failed unexpectedly.")


def _sudo_available() -> bool:
    try:
        result = subprocess.run(
            ["sudo", "--version"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
