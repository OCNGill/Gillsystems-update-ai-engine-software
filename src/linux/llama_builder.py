"""
llama_builder.py (Linux) — Builds llama.cpp with HIP/ROCm backend on Linux.

Clones or pulls latest llama.cpp, configures CMake with GGML_HIP=ON and
the detected AMDGPU_TARGETS, builds with all available cores, then installs
the binaries to the configured path.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GASUConfig

logger = logging.getLogger(__name__)


class LlamaBuilderLinux:
    """Clones, builds, and installs llama.cpp on Linux with AMD HIP."""

    def __init__(self, cfg: GASUConfig, gpu_targets: List[str]) -> None:
        self.cfg = cfg
        self.gpu_targets = gpu_targets
        self.source_dir = Path(cfg.paths.llama_cpp_source).expanduser()
        self.install_dir = Path(cfg.paths.llama_cpp_install_linux)
        self.build_dir = self.source_dir / "build-hip"

    def build_and_install(self) -> None:
        """Full clone → cmake configure → build → install cycle."""
        self._preflight_check()
        self._clone_or_pull()
        self._configure_cmake()
        self._build()
        self._install()
        self._validate()

    # ------------------------------------------------------------------
    # Pre-flight
    # ------------------------------------------------------------------

    def _preflight_check(self) -> None:
        """Ensure cmake, ninja, and hipcc are available."""
        required_tools = ["cmake", "git", "hipcc"]
        optional_tools = ["ninja"]

        for tool in required_tools:
            if not shutil.which(tool):
                raise RuntimeError(
                    f"Required tool '{tool}' not found. "
                    "Install cmake, git, and ROCm HIP SDK before proceeding."
                )

        self._use_ninja = bool(shutil.which("ninja"))
        if not self._use_ninja:
            print_warning("ninja not found — falling back to make (slower build).")
        else:
            print_info("Using Ninja build system for faster compilation.")

        if self.cfg.behavior.dry_run:
            print_dry_run("Pre-flight checks passed (dry-run).")

    # ------------------------------------------------------------------
    # Clone / pull
    # ------------------------------------------------------------------

    def _clone_or_pull(self) -> None:
        repo_url = self.cfg.repo.llama_cpp_repo

        if self.cfg.behavior.dry_run:
            if self.source_dir.exists():
                print_dry_run(f"Would pull latest: git -C {self.source_dir} pull")
            else:
                print_dry_run(f"Would clone {repo_url} → {self.source_dir}")
            return

        if (self.source_dir / ".git").exists():
            print_step(f"Pulling latest llama.cpp in {self.source_dir}...")
            _run(["git", "-C", str(self.source_dir), "pull", "--ff-only"])
            print_success("Repository updated.")
        else:
            print_step(f"Cloning llama.cpp from {repo_url}...")
            self.source_dir.parent.mkdir(parents=True, exist_ok=True)
            _run(["git", "clone", "--depth=1", repo_url, str(self.source_dir)])
            print_success(f"Cloned to {self.source_dir}")

    # ------------------------------------------------------------------
    # CMake configure
    # ------------------------------------------------------------------

    def _configure_cmake(self) -> None:
        targets_str = ";".join(self.gpu_targets)

        cmake_args = [
            "cmake",
            "-S", str(self.source_dir),
            "-B", str(self.build_dir),
            f"-DAMDGPU_TARGETS={targets_str}",
            "-DGGML_HIP=ON",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={self.install_dir}",
        ]

        if self._use_ninja:
            cmake_args += ["-GNinja"]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would configure: {' '.join(cmake_args)}")
            return

        print_step(f"Configuring CMake (targets: {targets_str})...")
        self.build_dir.mkdir(parents=True, exist_ok=True)
        _run(cmake_args)
        print_success("CMake configuration complete.")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        n_jobs = os.cpu_count() or 4

        if self._use_ninja:
            build_cmd = ["ninja", "-C", str(self.build_dir), f"-j{n_jobs}"]
        else:
            build_cmd = [
                "cmake", "--build", str(self.build_dir),
                "--config", "Release",
                f"-j{n_jobs}",
            ]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would build with {n_jobs} cores: {' '.join(build_cmd)}")
            return

        print_step(f"Building llama.cpp with {n_jobs} cores...")
        _run(build_cmd)
        print_success("Build complete.")

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _install(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would install binaries to {self.install_dir}")
            return

        install_cmd = ["cmake", "--install", str(self.build_dir), "--prefix", str(self.install_dir)]
        print_step(f"Installing binaries to {self.install_dir}...")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        _run(install_cmd)
        print_success(f"Installed to {self.install_dir}")

        # Symlink the binaries into /usr/local/bin for convenience
        bin_dir = self.install_dir / "bin"
        if bin_dir.exists():
            _symlink_binaries(bin_dir, Path("/usr/local/bin"))

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: llama-cli --version")
            return

        for binary in ("llama-cli", "llama-server"):
            binary_path = self.install_dir / "bin" / binary
            if binary_path.exists():
                try:
                    result = subprocess.run(
                        [str(binary_path), "--version"],
                        capture_output=True, text=True, timeout=10
                    )
                    output = (result.stdout + result.stderr).strip().split("\n")[0]
                    print_success(f"{binary}: {output[:80]}")
                    return
                except Exception as exc:
                    print_warning(f"Could not run {binary}: {exc}")

        print_warning("Could not validate llama.cpp binary — check installation manually.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: int = 3600) -> None:
    """Run a command, streaming output to the terminal. Raises on failure."""
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _symlink_binaries(src_dir: Path, dest_dir: Path) -> None:
    """Create symlinks in dest_dir pointing to binaries in src_dir."""
    for binary in src_dir.iterdir():
        if binary.is_file() and os.access(str(binary), os.X_OK):
            link = dest_dir / binary.name
            try:
                if link.exists() or link.is_symlink():
                    link.unlink()
                link.symlink_to(binary)
                logger.debug("Symlinked %s → %s", binary, link)
            except OSError as exc:
                logger.warning("Could not symlink %s: %s", binary, exc)
