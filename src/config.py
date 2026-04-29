"""
config.py — Pydantic configuration models for Gillsystems AI Stack Updater.

Loads from config/default_config.yaml with environment variable overrides.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class GpuConfig(BaseModel):
    """GPU architecture targets for CMake."""
    targets: List[str] = Field(
        default=["gfx1100", "gfx1101", "gfx1030"],
        description="AMDGPU_TARGETS passed to CMake.",
    )
    auto_detect: bool = Field(
        default=True,
        description="Attempt runtime GPU architecture detection.",
    )


class PathsConfig(BaseModel):
    """Install and workspace paths."""
    llama_cpp_install_linux: str = Field(default="/opt/gillsystems/llama.cpp")
    llama_cpp_install_windows: str = Field(default="C:\\Gillsystems\\llama.cpp")
    llama_cpp_source: str = Field(default="~/src/llama.cpp")
    state_dir: str = Field(default="state")
    log_dir: str = Field(default="logs")


class RepoConfig(BaseModel):
    """Upstream source repositories."""
    llama_cpp_repo: str = Field(default="https://github.com/ggml-org/llama.cpp.git")
    llama_cpp_github_api: str = Field(
        default="https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
    )
    rocm_repo_base: str = Field(
        default="https://repo.radeon.com/amdgpu-install/latest"
    )
    hip_sdk_download_base: str = Field(
        default="https://repo.radeon.com/rocm/msi"
    )


class BehaviorConfig(BaseModel):
    """Runtime behavior toggles."""
    dry_run: bool = Field(default=False)
    auto_yes: bool = Field(default=False)
    force: bool = Field(default=False)
    verbose: bool = Field(default=False)
    reboot_countdown_seconds: int = Field(default=30)
    auto_reboot: bool = Field(default=True)
    update_python_bindings: bool = Field(default=False)
    rocm_usecases: List[str] = Field(default=["rocm", "hiplibsdk"])


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class GillsystemsAIStackUpdaterConfig(BaseModel):
    """Root configuration object for Gillsystems AI Stack Updater."""
    gpu: GpuConfig = Field(default_factory=GpuConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    repo: RepoConfig = Field(default_factory=RepoConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    log_level: str = Field(default="INFO")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _resolve_config_path() -> Path:
    """Find default_config.yaml relative to the project root."""
    # Walk up from this file to find project root (contains pyproject.toml)
    here = Path(__file__).resolve().parent
    for candidate in [here.parent, here.parent.parent]:
        cfg = candidate / "config" / "default_config.yaml"
        if cfg.exists():
            return cfg
    # Return the expected path even if it doesn't exist yet
    return here.parent / "config" / "default_config.yaml"


def load_config(
    config_path: Optional[Path] = None,
    dry_run: bool = False,
    auto_yes: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> GillsystemsAIStackUpdaterConfig:
    """
    Load configuration from YAML file and apply CLI flag overrides.

    Args:
        config_path: Optional explicit path to YAML config file.
        dry_run: Override behavior.dry_run.
        auto_yes: Override behavior.auto_yes.
        force: Override behavior.force.
        verbose: Override behavior.verbose.

    Returns:
        GillsystemsAIStackUpdaterConfig instance.
    """
    path = config_path or _resolve_config_path()

    raw: dict = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    cfg = GillsystemsAIStackUpdaterConfig.model_validate(raw)

    # CLI flag overrides
    if dry_run:
        cfg.behavior.dry_run = True
    if auto_yes:
        cfg.behavior.auto_yes = True
    if force:
        cfg.behavior.force = True
    if verbose:
        cfg.behavior.verbose = True

    # Environment variable overrides
    if os.environ.get("GILLSYSTEMS_AI_STACK_UPDATER_DRY_RUN", "").lower() in ("1", "true", "yes"):
        cfg.behavior.dry_run = True
    if os.environ.get("GILLSYSTEMS_AI_STACK_UPDATER_VERBOSE", "").lower() in ("1", "true", "yes"):
        cfg.behavior.verbose = True
    if os.environ.get("GILLSYSTEMS_AI_STACK_UPDATER_LOG_LEVEL"):
        cfg.log_level = os.environ["GILLSYSTEMS_AI_STACK_UPDATER_LOG_LEVEL"].upper()

    return cfg
