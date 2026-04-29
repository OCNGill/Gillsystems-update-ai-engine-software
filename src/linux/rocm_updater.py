"""
rocm_updater.py — Linux ROCm/HIP updater sub-agent.

Handles amdgpu-install automation, package downloads, user group membership,
and post-install validation on Ubuntu/Fedora.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig

logger = logging.getLogger(__name__)

# AMD amdgpu-install download base URL (latest symlink)
_AMDGPU_INSTALL_BASE = "https://repo.radeon.com/amdgpu-install/latest/ubuntu"


class ROCmUpdater:
    """Installs/upgrades ROCm on Linux using amdgpu-install."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig) -> None:
        self.cfg = cfg

    def update(self) -> bool:
        """
        Run the full ROCm/HIP update cycle.

        Returns:
            True if a system reboot is required, False otherwise.
        """
        distro = _detect_distro()
        print_info(f"Detected Linux distribution: {distro}")

        # Step 1: Download amdgpu-install
        installer_path = self._download_amdgpu_install(distro)
        if not installer_path:
            raise RuntimeError("Failed to download amdgpu-install. Cannot continue.")

        # Step 2: Install the amdgpu-install package
        self._install_package(installer_path, distro)

        # Step 3: Run amdgpu-install with ROCm usecases
        reboot_required = self._run_amdgpu_install()

        # Step 4: Add user to render/video groups
        self._add_user_to_gpu_groups()

        # Step 5: Post-install validation
        self._validate_installation()

        return reboot_required

    # ------------------------------------------------------------------
    # Download amdgpu-install
    # ------------------------------------------------------------------

    def _download_amdgpu_install(self, distro: str) -> Optional[Path]:
        """Download the amdgpu-install .deb or .rpm package."""
        url = self._build_installer_url(distro)
        if not url:
            print_warning(f"Unknown distro '{distro}' — cannot construct amdgpu-install URL.")
            return None

        print_step(f"Downloading amdgpu-install from: {url}")

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would download: {url}")
            return Path("/tmp/amdgpu-install-dry-run.deb")

        suffix = ".deb" if _is_debian_based(distro) else ".rpm"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="amdgpu-install-")
        os.close(tmp_fd)

        try:
            urllib.request.urlretrieve(url, tmp_path)
            print_success(f"Downloaded to {tmp_path}")
            return Path(tmp_path)
        except Exception as exc:
            print_error(f"Download failed: {exc}")
            return None

    def _build_installer_url(self, distro: str) -> Optional[str]:
        """
        Construct the amdgpu-install download URL for the given distro.
        The URL format follows AMD's repo structure.
        """
        # Ubuntu: https://repo.radeon.com/amdgpu-install/latest/ubuntu/<codename>/
        #   filename: amdgpu-install_<version>~<codename>_all.deb
        # RHEL/Fedora: https://repo.radeon.com/amdgpu-install/latest/rhel/<version>/
        #   filename: amdgpu-install-<version>.<arch>.rpm
        base = self.cfg.repo.rocm_repo_base

        if "ubuntu" in distro:
            codename = _ubuntu_codename()
            return f"{base}/ubuntu/{codename}/"
        elif "centos" in distro or "rhel" in distro or "fedora" in distro:
            rhel_ver = _rhel_major_version()
            return f"{base}/rhel/{rhel_ver}/"

        return None

    # ------------------------------------------------------------------
    # Install the .deb / .rpm
    # ------------------------------------------------------------------

    def _install_package(self, pkg_path: Path, distro: str) -> None:
        """Install the amdgpu-install package with the appropriate package manager."""
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would install package: {pkg_path}")
            return

        if _is_debian_based(distro):
            print_step(f"Installing {pkg_path.name} with apt...")
            _run_privileged(["apt-get", "install", "-y", str(pkg_path)])
        else:
            print_step(f"Installing {pkg_path.name} with rpm...")
            _run_privileged(["rpm", "-i", "--force", str(pkg_path)])

        print_success("amdgpu-install package installed.")

    # ------------------------------------------------------------------
    # Run amdgpu-install
    # ------------------------------------------------------------------

    def _run_amdgpu_install(self) -> bool:
        """
        Execute 'amdgpu-install --usecase=<usecases> -y'.

        Returns True if a reboot is required (kernel driver was updated).
        """
        usecases = ",".join(self.cfg.behavior.rocm_usecases)
        cmd = ["amdgpu-install", f"--usecase={usecases}", "--no-dkms", "-y"]

        print_step(f"Running: {' '.join(cmd)}")

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would run: {' '.join(cmd)}")
            return False

        result = _run_privileged(cmd, capture=True)

        # Detect if kernel driver update occurred (reboot needed)
        combined = (result.stdout or "") + (result.stderr or "")
        reboot_hints = [
            "reboot",
            "restart",
            "kernel module",
            "dkms",
        ]
        reboot_required = any(hint in combined.lower() for hint in reboot_hints)

        if reboot_required:
            print_warning("Kernel driver update detected — reboot required.")
        else:
            print_success("ROCm/HIP packages installed successfully.")

        return reboot_required

    # ------------------------------------------------------------------
    # GPU group management
    # ------------------------------------------------------------------

    def _add_user_to_gpu_groups(self) -> None:
        """Add the invoking non-root user to render and video groups."""
        # SUDO_USER is set when running under sudo — it's the original username
        username = os.environ.get("SUDO_USER") or os.environ.get("USER")
        if not username or username == "root":
            print_step("Running as root user — skipping group addition.")
            return

        for group in ("render", "video"):
            if self.cfg.behavior.dry_run:
                print_dry_run(f"Would add user '{username}' to group '{group}'")
                continue
            try:
                _run_privileged(["usermod", "-aG", group, username])
                print_success(f"Added '{username}' to group '{group}'")
            except Exception as exc:
                print_warning(f"Could not add user to group '{group}': {exc}")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_installation(self) -> None:
        """Run basic sanity checks after installation."""
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: rocm-smi --version, hipcc --version, rocminfo")
            return

        checks = [
            (["rocm-smi", "--version"],  "rocm-smi"),
            (["hipcc", "--version"],      "hipcc"),
        ]
        for cmd, name in checks:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    first_line = (result.stdout + result.stderr).strip().split("\n")[0]
                    print_success(f"{name}: {first_line[:80]}")
                else:
                    print_warning(f"{name} returned non-zero (may need reboot)")
            except FileNotFoundError:
                print_warning(f"{name} not found — may require reboot or PATH update")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_distro() -> str:
    """Return a lowercase distro identifier string."""
    try:
        info = platform.freedesktop_os_release()
        return (info.get("ID", "") + " " + info.get("ID_LIKE", "")).lower().strip()
    except AttributeError:
        # Python < 3.10 fallback
        try:
            with open("/etc/os-release") as fh:
                content = fh.read().lower()
            return content
        except OSError:
            return ""


def _is_debian_based(distro: str) -> bool:
    return any(k in distro for k in ("ubuntu", "debian", "mint", "pop"))


def _ubuntu_codename() -> str:
    try:
        info = platform.freedesktop_os_release()
        codename = info.get("VERSION_CODENAME", "")
        if codename:
            return codename
    except AttributeError:
        pass
    result = subprocess.run(["lsb_release", "-cs"], capture_output=True, text=True)
    return result.stdout.strip() or "jammy"


def _rhel_major_version() -> str:
    try:
        info = platform.freedesktop_os_release()
        ver = info.get("VERSION_ID", "8").split(".")[0]
        return ver
    except Exception:
        return "8"


def _run_privileged(
    cmd: list[str],
    capture: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a shell command.  If not root, prepend sudo.
    Raises CalledProcessError on failure.
    """
    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=True,
        timeout=600,  # 10 min max
    )
    return result
