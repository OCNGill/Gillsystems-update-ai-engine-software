"""
reboot_handler.py (Windows) — Registers a one-shot Scheduled Task for post-reboot resume.

Creates a Windows Scheduled Task that runs update-ai-stack.bat --resume at
the next user logon. After a successful resume the task self-deletes.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from src.cli import print_dry_run, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig

logger = logging.getLogger(__name__)

_TASK_NAME = "GillsystemsAIStackUpdaterResumeTask"


class RebootHandler:
    """Manages a Windows Scheduled Task for reboot-resume and triggers reboots."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig) -> None:
        self.cfg = cfg
        self.launcher_path = self._find_launcher()

    def _find_launcher(self) -> Path:
        """Locate update-ai-stack.bat relative to this module."""
        here = Path(__file__).resolve().parent
        for candidate in [here.parent.parent, here.parent.parent.parent]:
            bat = candidate / "update-ai-stack.bat"
            if bat.exists():
                return bat
        return here.parent.parent / "update-ai-stack.bat"

    def register_resume_task(self) -> None:
        """Create a one-shot logon Scheduled Task for resume."""
        if self.cfg.behavior.dry_run:
            print_dry_run(
                f"Would create Scheduled Task '{_TASK_NAME}' to run:\n"
                f"  {self.launcher_path} --resume"
            )
            return

        # Build the schtasks command
        # /SC ONLOGON = trigger at next logon
        # /RL HIGHEST = run with highest privileges
        # /TR = task run command
        # /RU "" = run as current user
        cmd = [
            "schtasks", "/create",
            "/tn", _TASK_NAME,
            "/tr", f'"{self.launcher_path}" --resume',
            "/sc", "ONLOGON",
            "/rl", "HIGHEST",
            "/f",          # force overwrite if exists
        ]

        print_step(f"Registering Scheduled Task: {_TASK_NAME}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            logger.debug("schtasks output: %s", result.stdout)
            print_success(f"Scheduled Task '{_TASK_NAME}' created successfully.")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Failed to create Scheduled Task: {exc.stderr or exc.stdout}"
            ) from exc

    def unregister_resume_task(self) -> None:
        """Delete the Scheduled Task after a successful resume."""
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would delete Scheduled Task '{_TASK_NAME}'")
            return

        print_step(f"Removing Scheduled Task: {_TASK_NAME}")
        cmd = ["schtasks", "/delete", "/tn", _TASK_NAME, "/f"]
        try:
            subprocess.run(cmd, capture_output=True, check=False, timeout=30)
            print_success(f"Scheduled Task '{_TASK_NAME}' removed.")
        except Exception as exc:
            print_warning(f"Could not remove Scheduled Task: {exc}")

    def reboot(self) -> None:
        """Initiate a Windows system reboot."""
        if self.cfg.behavior.dry_run:
            print_dry_run("Would run: shutdown /r /t 10 /c 'Gillsystems AI Stack Updater: Reboot for driver installation'")
            return

        print_info("Initiating system reboot in 10 seconds...")
        subprocess.run(
            [
                "shutdown", "/r", "/t", "10",
                "/c", "Gillsystems AI Stack Updater: Rebooting to complete AMD driver installation",
            ],
            check=True,
            timeout=15,
        )

    def abort_reboot(self) -> None:
        """Cancel a pending reboot (e.g., if user cancels)."""
        try:
            subprocess.run(["shutdown", "/a"], check=False, timeout=10)
            print_info("Reboot aborted.")
        except Exception:
            pass
