"""
version_intel.py — Version Intelligence for Gillsystems AI Stack Updater.

Queries GitHub Releases API for llama.cpp and AMD repos for ROCm/HIP,
then compares against locally installed versions to produce an UpdateManifest.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

import httpx
from packaging.version import Version, InvalidVersion


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ComponentVersion:
    name: str
    installed: Optional[str]   # None = not installed
    latest: Optional[str]      # None = could not determine
    needs_update: bool = False
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.installed and self.latest and not self.needs_update:
            self.needs_update = _version_lt(self.installed, self.latest)


@dataclass
class UpdateManifest:
    rocm: ComponentVersion
    llama_cpp: ComponentVersion
    any_updates: bool = field(init=False)

    def __post_init__(self) -> None:
        self.any_updates = self.rocm.needs_update or self.llama_cpp.needs_update

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        for comp in (self.rocm, self.llama_cpp):
            installed_str = comp.installed or "not installed"
            latest_str = comp.latest or "unknown"
            status = "UPDATE AVAILABLE" if comp.needs_update else "current"
            if comp.error:
                status = f"ERROR: {comp.error}"
            lines.append(
                f"  {comp.name:<18} installed={installed_str:<15} latest={latest_str:<15} [{status}]"
            )
        return lines


# ---------------------------------------------------------------------------
# Version Intel class
# ---------------------------------------------------------------------------


class VersionIntel:
    """Checks installed and upstream versions for ROCm/HIP and llama.cpp."""

    GITHUB_LLAMA_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
    ROCM_VERSION_URL = "https://repo.radeon.com/rocm/apt/latest/dists/focal/Release"

    def __init__(self, timeout: int = 15, bleeding_edge: bool = False) -> None:
        self._timeout = timeout
        self._bleeding_edge = bleeding_edge

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_all(self) -> UpdateManifest:
        """Run all version checks and return an UpdateManifest."""
        rocm = self._check_rocm()
        llama = self._check_llama_cpp()
        return UpdateManifest(rocm=rocm, llama_cpp=llama)

    # ------------------------------------------------------------------
    # ROCm / HIP
    # ------------------------------------------------------------------

    def _check_rocm(self) -> ComponentVersion:
        installed = self._get_installed_rocm()
        latest, err = self._get_latest_rocm()
        return ComponentVersion(
            name="ROCm/HIP",
            installed=installed,
            latest=latest,
            error=err,
        )

    def _get_installed_rocm(self) -> Optional[str]:
        """
        Try multiple strategies to determine the installed ROCm version.
        Returns a version string like '6.3.1' or None.
        """
        strategies = [
            self._rocm_via_rocm_smi,
            self._rocm_via_hipcc,
            self._rocm_via_version_file,
        ]
        for fn in strategies:
            result = fn()
            if result:
                return result
        return None

    def _rocm_via_rocm_smi(self) -> Optional[str]:
        try:
            out = _run(["rocm-smi", "--version"])
            # Output looks like: "ROCm System Management Interface (RSMI) version: 6.3.1"
            match = re.search(r"version[:\s]+(\d+\.\d+[\.\d]*)", out, re.IGNORECASE)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _rocm_via_hipcc(self) -> Optional[str]:
        try:
            out = _run(["hipcc", "--version"])
            # "HIP version: 6.3.42134-..." or "AMD clang version ..."
            match = re.search(r"HIP version[:\s]+(\d+\.\d+[\.\d]*)", out, re.IGNORECASE)
            if match:
                return match.group(1)
            # Fallback: look for ROCm in the string
            match = re.search(r"ROCm[- _](\d+\.\d+[\.\d]*)", out, re.IGNORECASE)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _rocm_via_version_file(self) -> Optional[str]:
        """Check /opt/rocm/.info/version or /opt/rocm/share/doc/rocm/version.txt"""
        if sys.platform == "linux":
            candidates = [
                "/opt/rocm/.info/version",
                "/opt/rocm/share/doc/rocm-core/ROCM_VERSION",
            ]
            for path in candidates:
                try:
                    with open(path, "r") as fh:
                        content = fh.read().strip()
                    match = re.search(r"(\d+\.\d+[\.\d]*)", content)
                    if match:
                        return match.group(1)
                except OSError:
                    continue
        return None

    def _get_latest_rocm(self) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch latest ROCm version from AMD's repo metadata.
        Returns (version_str, error_msg).
        """
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                # Try the latest symlink release page
                resp = client.get(
                    "https://repo.radeon.com/rocm/apt/latest/dists/focal/Release"
                )
                # Look for Version: field in apt Release file
                match = re.search(r"Version:\s*(\d+\.\d+[\.\d]*)", resp.text)
                if match:
                    return match.group(1), None
        except Exception:
            pass

        # Fallback: scrape the ROCm GitHub releases
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                resp = client.get(
                    "https://api.github.com/repos/ROCm/ROCm/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tag = data.get("tag_name", "")
                    match = re.search(r"(\d+\.\d+[\.\d]*)", tag)
                    if match:
                        return match.group(1), None
        except Exception as exc:
            return None, str(exc)

        return None, "Could not determine latest ROCm version"

    # ------------------------------------------------------------------
    # llama.cpp
    # ------------------------------------------------------------------

    def _check_llama_cpp(self) -> ComponentVersion:
        installed = self._get_installed_llama()
        latest, err = self._get_latest_llama()
        return ComponentVersion(
            name="llama.cpp",
            installed=installed,
            latest=latest,
            error=err,
        )

    def _get_installed_llama(self) -> Optional[str]:
        """
        Try llama-cli --version or llama-server --version.
        llama.cpp uses build numbers like 'b3682' or short git hashes.
        """
        for binary in ("llama-cli", "llama-server", "main"):
            try:
                out = _run([binary, "--version"])
                # 'version: 3682 (abc1234)' or just 'b3682'
                match = re.search(r"b(?:uild[:\s]+)?(\d{3,6})", out, re.IGNORECASE)
                if match:
                    return f"b{match.group(1)}"
                # Alternative: 'version: 3682'
                match = re.search(r"version[:\s]+(\d{3,6})", out, re.IGNORECASE)
                if match:
                    return f"b{match.group(1)}"
            except Exception:
                continue
        return None

    def _get_latest_llama(self) -> tuple[Optional[str], Optional[str]]:
        """Query GitHub API for the latest llama.cpp release tag."""
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                resp = client.get(
                    self.GITHUB_LLAMA_URL,
                    headers={"Accept": "application/vnd.github+json"},
                )
                resp.raise_for_status()
                data = resp.json()
                tag = data.get("tag_name", "")
                if self._bleeding_edge:
                    # In bleeding edge mode, we don't care about the tag, 
                    # we return 'master' to signify we want the latest.
                    return "master (bleeding-edge)", None
                if tag:
                    return tag, None
                return None, "No tag_name in GitHub response"
        except httpx.HTTPStatusError as exc:
            return None, f"GitHub API HTTP {exc.response.status_code}"
        except Exception as exc:
            return None, str(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str]) -> str:
    """Run a subprocess and return combined stdout+stderr as a string."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return (result.stdout + result.stderr).strip()


def _version_lt(installed: str, latest: str) -> bool:
    """Return True if installed < latest using smart comparison."""
    # Handle llama.cpp build tags like 'b3682'
    installed_num = re.search(r"b(\d+)", installed)
    latest_num = re.search(r"b(\d+)", latest)
    if installed_num and latest_num:
        return int(installed_num.group(1)) < int(latest_num.group(1))

    if "master" in latest:
        return True  # Always update in bleeding-edge mode

    # Try semver comparison
    try:
        return Version(installed) < Version(latest)
    except InvalidVersion:
        # Fall back to string comparison
        return installed != latest
