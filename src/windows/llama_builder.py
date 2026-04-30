"""
llama_builder.py (Windows) — Builds llama.cpp with AMD HIP backend on Windows.

Detects VS Build Tools / Developer Command Prompt, clones/pulls llama.cpp,
configures CMake with HIP backend, and builds with Ninja or MSBuild.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from src.cli import print_dry_run, print_error, print_info, print_step, print_success, print_warning
from src.config import GillsystemsAIStackUpdaterConfig
from src.gpu_detect import get_compute_tier

logger = logging.getLogger(__name__)

# VS Developer Command Prompt vcvarsall.bat search paths
_VCVARS_SEARCH_PATHS: list[str] = [
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat",
    r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
]


class LlamaBuilderWindows:
    """Clones, builds, and installs llama.cpp on Windows with AMD HIP."""

    def __init__(self, cfg: GillsystemsAIStackUpdaterConfig, gpu_targets: List[str]) -> None:
        self.cfg = cfg
        self.gpu_targets = gpu_targets
        self.source_dir = Path(cfg.paths.llama_cpp_source).expanduser()
        self.install_dir = Path(cfg.paths.llama_cpp_install_windows)
        self.build_dir = self.source_dir / "build-hip-win"
        self._vcvars: Optional[Path] = None
        self._use_ninja: bool = False

    def build_and_install(self) -> None:
        """Full clone → configure → build → install cycle."""
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
        """Ensure cmake, git, and HIP SDK are available."""
        for tool in ("cmake", "git"):
            if not shutil.which(tool):
                raise RuntimeError(
                    f"Required tool '{tool}' not found. Install it before proceeding."
                )

        tier = get_compute_tier(self.gpu_targets)
        if not shutil.which("hipcc"):
            if tier == 1:
                raise RuntimeError(
                    "hipcc not found. Tier 1 hardware REQUIRES the AMD HIP SDK. "
                    "Install it and ensure it is on PATH before proceeding."
                )
            else:
                print_warning("hipcc not found. Tier 2 hardware detected — falling back to Vulkan.")

        # Locate vcvarsall.bat
        for path_str in _VCVARS_SEARCH_PATHS:
            p = Path(path_str)
            if p.exists():
                self._vcvars = p
                break

        if not self._vcvars:
            if tier == 1:
                raise RuntimeError(
                    "Visual Studio Build Tools not found. "
                    "Tier 1 hardware requires MSVC for optimized ROCm/HIP compilation."
                )
            print_warning(
                "Visual Studio Build Tools not found. "
                "Attempting without vcvarsall.bat — build may fail."
            )

        # Prefer Ninja
        self._use_ninja = bool(shutil.which("ninja"))
        if not self._use_ninja:
            print_warning("Ninja not found — falling back to MSBuild (slower build).")
        else:
            print_info("Using Ninja build system.")

        if self.cfg.behavior.dry_run:
            print_dry_run("Pre-flight checks passed (dry-run).")

    # ------------------------------------------------------------------
    # Clone / Pull
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

        # Find HIP_PATH from environment or default location
        hip_path = os.environ.get("HIP_PATH", _find_hip_path())
        use_hip = bool(shutil.which("hipcc"))

        cmake_args = [
            "cmake",
            "-S", str(self.source_dir),
            "-B", str(self.build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={self.install_dir}",
        ]

        if use_hip:
            cmake_args += [
                f"-DAMDGPU_TARGETS={targets_str}",
                "-DGGML_HIP=ON",
                "-DGGML_HIP_ROCWMMA_FATTN=ON",
            ]
            if hip_path:
                cmake_args.append(f"-DHIP_PATH={hip_path}")
        else:
            cmake_args.append("-DGGML_VULKAN=ON")
            print_info("Enabling Vulkan backend (HIP fallback for mobile/edge targets).")

        if self._use_ninja:
            cmake_args += ["-GNinja"]
            if use_hip and hip_path:
                cmake_args += [
                    f"-DCMAKE_C_COMPILER={hip_path}/bin/clang.exe",
                    f"-DCMAKE_CXX_COMPILER={hip_path}/bin/clang++.exe",
                ]
        else:
            cmake_args += ["-G", "Visual Studio 17 2022", "-A", "x64"]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would configure: {' '.join(cmake_args)}")
            return

        print_step(f"Configuring CMake (targets: {targets_str})...")
        self.build_dir.mkdir(parents=True, exist_ok=True)

        env = _build_env(self._vcvars) if self._vcvars else None
        _run(cmake_args, env=env)
        print_success("CMake configuration complete.")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        n_jobs = os.cpu_count() or 4

        env = _build_env(self._vcvars) if self._vcvars else os.environ.copy()
        if get_compute_tier(self.gpu_targets) == 2:
            print_info("Tier 2 Mobile/Edge architecture detected. Injecting LLAMA_HIP_UMA=1.")
            env["LLAMA_HIP_UMA"] = "1"

        if self._use_ninja:
            build_cmd = ["ninja", "-C", str(self.build_dir), f"-j{n_jobs}"]
        else:
            build_cmd = [
                "cmake", "--build", str(self.build_dir),
                "--config", "Release",
                f"--parallel", str(n_jobs),
            ]

        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would build with {n_jobs} cores: {' '.join(build_cmd)}")
            return

        print_step(f"Building llama.cpp with {n_jobs} cores...")
        _run(build_cmd, env=env)
        print_success("Build complete.")

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def _install(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run(f"Would install binaries to {self.install_dir}")
            return

        install_cmd = [
            "cmake", "--install", str(self.build_dir),
            "--config", "Release",
            "--prefix", str(self.install_dir),
        ]
        print_step(f"Installing binaries to {self.install_dir}...")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        _run(install_cmd)
        print_success(f"Installed to {self.install_dir}")

        # Add install bin dir to user PATH in registry
        bin_dir = str(self.install_dir / "bin")
        _append_to_user_path(bin_dir)
        print_info(f"Added {bin_dir} to user PATH.")

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        if self.cfg.behavior.dry_run:
            print_dry_run("Would validate: llama-cli.exe --version")
            return

        for binary in ("llama-cli.exe", "llama-server.exe", "main.exe"):
            bin_path = self.install_dir / "bin" / binary
            if bin_path.exists():
                try:
                    result = subprocess.run(
                        [str(bin_path), "--version"],
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


def _find_hip_path() -> Optional[str]:
    """Try to locate the HIP SDK installation directory."""
    candidates = [
        r"C:\Program Files\AMD\ROCm\6.3",
        r"C:\Program Files\AMD\ROCm\6.2",
        r"C:\Program Files\AMD\ROCm\6.1",
        r"C:\Program Files\AMD\ROCm",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _build_env(vcvars: Path) -> dict:
    """
    Return an environment dict that includes VS build tool variables.
    Runs vcvarsall.bat and captures the resulting environment.
    """
    script = f'call "{vcvars}" amd64 && set'
    result = subprocess.run(
        ["cmd", "/c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env or None


def _run(cmd: list[str], timeout: int = 3600, env: Optional[dict] = None) -> None:
    """Run a command; raises on failure."""
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _append_to_user_path(new_dir: str) -> None:
    """Add a directory to the current user's PATH in the registry."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
        )
        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""
        paths = [p.strip() for p in current_path.split(";") if p.strip()]
        if new_dir not in paths:
            paths.append(new_dir)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(paths))
        winreg.CloseKey(key)
    except Exception as exc:
        logger.warning("Could not update user PATH: %s", exc)
