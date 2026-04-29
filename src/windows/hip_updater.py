"""
hip_updater.py — Windows HIP SDK silent installer sub-agent.

Downloads the latest AMD HIP SDK installer for Windows, runs it silently,
updates environment variables, and validates the installation.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import urllib.request
import winreg
from pathlib import Path
from typing import Optional

import httpx

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig

logger = logging.getLogger(__name__)

# AMD HIP SDK download index page
_HIP_SDK_RELEASES_URL = "https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html"
_HIP_SDK_DOWNLOAD_BASE = "https://repo.radeon.com/rocm/msi"


class HIPUpdater:
    """Downloads and silently installs the AMD HIP SDK on Windows."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig) -> None:
        self.cfg = cfg

    def update(self) -> bool:
        """
        Run the full HIP SDK update cycle.

        Returns:
            True if a reboot is required, False otherwise.
        """
        # Step 1: Find the latest HIP SDK installer URL
        installer_url, version_str = self._find_latest_installer()
        if not installer_url:
            print_warning("Could not locate HIP SDK installer URL. Skipping Windows HIP update.")
            return False

        print_info(f"Latest HIP SDK version: {version_str or 'unknown'}")

        # Step 2: Download the installer
        installer_path = self._download_installer(installer_url)
        if not installer_path:
            raise RuntimeError("HIP SDK download failed.")

        # Step 3: Run silent install
        reboot_required = self._run_silent_install(installer_path, version_str)

        # Step 4: Update environment variables
        self._update_environment_variables()

        # Step 5: Validate
        self._validate_installation()

        # Clean up temp installer
        if installer_path.exists() and not self.cfg.behavior.dry_run:
            try:
                installer_path.unlink()
            except OSError:
                pass

        return reboot_required

    # ------------------------------------------------------------------
    # Locate latest installer
    # ------------------------------------------------------------------

    def _find_latest_installer(self) -> tuple[Optional[str], Optional[str]]:
        """
        Try to resolve the latest HIP SDK EXE download URL.

        Returns (url, version_string) or (None, None) on failure.
        """
        base = self.cfg.repo.hip_sdk_download_base

        # Try common recent patterns:
        # https://repo.radeon.com/rocm/msi/<version>/HIP-SDK-Installer-<version>.0.exe
        known_recent = ["6.3.1", "6.3.0", "6.2.4", "6.2.0", "6.1.0"]

        with httpx.Client(timeout=15, follow_redirects=True) as client:
            for ver in known_recent:
                url = f"{base}/{ver}/HIP-SDK-Installer-{ver}.0.exe"
                try:
                    resp = client.head(url)
                    if resp.status_code == 200:
                        return url, ver
                except Exception:
                    continue

        # Fallback: return latest known (user can also manually pin in config)
        url = f"{base}/6.3.1/HIP-SDK-Installer-6.3.1.0.exe"
        return url, "6.3.1"

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download_installer(self, url: str) -> Optional[Path]:
        """Download the HIP SDK installer EXE."""
        print_step(f"Downloading HIP SDK installer: {url}")

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would download: {url}")
            return Path(tempfile.gettempdir()) / "HIP-SDK-Installer-dry-run.exe"

        tmp_dir = Path(tempfile.gettempdir())
        filename = url.split("/")[-1]
        dest = tmp_dir / filename

        try:
            urllib.request.urlretrieve(url, str(dest))
            print_success(f"Downloaded to {dest}")
            return dest
        except Exception as exc:
            print_error(f"Download failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Silent install
    # ------------------------------------------------------------------

    def _run_silent_install(self, installer_path: Path, version: Optional[str]) -> bool:
        """
        Run the HIP SDK installer silently.

        Returns True if a reboot is required.
        """
        # AMD HIP SDK installer supports /S for NSIS silent mode
        # Some versions use MSI: msiexec /i "..." /qn /norestart
        cmd = [str(installer_path), "/S", "/v/qn", "/norestart"]

        print_step(f"Running silent install: {installer_path.name}")

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would run: {' '.join(cmd)}")
            return False

        try:
            result = subprocess.run(
                cmd,
                timeout=900,  # 15 min
                check=False,
            )
            # Exit code 3010 = success with reboot required (MSI convention)
            if result.returncode == 3010:
                print_warning("HIP SDK installed — reboot required.")
                return True
            elif result.returncode == 0:
                print_success(f"HIP SDK {version or ''} installed successfully.")
                return False
            else:
                raise RuntimeError(
                    f"HIP SDK installer exited with code {result.returncode}. "
                    "Check Windows Event Viewer for details."
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError("HIP SDK installer timed out after 15 minutes.")

    # ------------------------------------------------------------------
    # Environment variables
    # ------------------------------------------------------------------

    def _update_environment_variables(self) -> None:
        """
        Ensure HIP_PATH, ROCM_PATH, and PATH are set in the system environment.
        These are typically set by the installer itself, but we verify and patch.
        """
        # Common HIP SDK install locations
        candidates = [
            Path("C:/Program Files/AMD/ROCm/6.3"),
            Path("C:/Program Files/AMD/ROCm/6.2"),
            Path("C:/Program Files/AMD/ROCm/6.1"),
            Path("C:/Program Files/AMD/ROCm"),
        ]

        hip_path: Optional[Path] = None
        for candidate in candidates:
            if (candidate / "bin" / "hipcc.exe").exists():
                hip_path = candidate
                break

        if not hip_path:
            print_warning("Could not locate HIP SDK install directory. Environment not updated.")
            return

        bin_path = str(hip_path / "bin")
        hip_path_str = str(hip_path)

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would set HIP_PATH={hip_path_str}")
            print_dry_run(f"Would set ROCM_PATH={hip_path_str}")
            print_dry_run(f"Would add to PATH: {bin_path}")
            return

        _set_system_env("HIP_PATH", hip_path_str)
        _set_system_env("ROCM_PATH", hip_path_str)
        _append_to_system_path(bin_path)
        print_success(f"Environment variables updated for HIP SDK at {hip_path}")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_installation(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: hipcc --version, hipInfo")
            return

        for exe in ("hipcc", "hipInfo"):
            try:
                result = subprocess.run(
                    [exe, "--version"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    output = (result.stdout + result.stderr).strip().split("\n")[0]
                    print_success(f"{exe}: {output[:80]}")
                    return
            except FileNotFoundError:
                continue

        print_warning("hipcc/hipInfo not found in PATH — may require restart of terminal or reboot.")


# ---------------------------------------------------------------------------
# Registry / environment helpers
# ---------------------------------------------------------------------------


def _set_system_env(name: str, value: str) -> None:
    """Write a system environment variable to the Windows registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        logger.debug("Set system env %s = %s", name, value)
    except OSError as exc:
        logger.warning("Could not set %s in registry: %s", name, exc)


def _append_to_system_path(new_dir: str) -> None:
    """Add a directory to the system PATH if not already present."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
        )
        current_path, _ = winreg.QueryValueEx(key, "Path")
        paths = [p.strip() for p in current_path.split(";") if p.strip()]
        if new_dir not in paths:
            paths.append(new_dir)
            updated = ";".join(paths)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated)
            logger.debug("Appended %s to system PATH", new_dir)
        winreg.CloseKey(key)
    except OSError as exc:
        logger.warning("Could not update system PATH: %s", exc)
