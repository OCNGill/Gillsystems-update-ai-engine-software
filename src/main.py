"""
main.py — GASU Orchestrator / Entry Point

Top-level state machine:
  CHECK → UPDATE_ROCM → [REBOOT? →] UPDATE_LLAMA → VALIDATE → DONE
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

from src import __version__
from src.cli import (
    confirm,
    print_banner,
    print_error,
    print_info,
    print_phase,
    print_step,
    print_success,
    print_summary,
    print_version_table,
    print_warning,
)
from src.config import load_config, GASUConfig
from src.gpu_detect import GPUDetector
from src.privilege import ensure_admin, is_admin
from src.state_manager import StateManager, StepStatus
from src.version_intel import VersionIntel, UpdateManifest

logger = logging.getLogger("gasu")


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gasu",
        description="Gillsystems AI Stack Updater — ROCm/HIP + llama.cpp",
    )
    parser.add_argument("--version", action="version", version=f"GASU {__version__}")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes.")
    parser.add_argument("--yes", "-y", action="store_true", dest="auto_yes", help="Auto-confirm all prompts.")
    parser.add_argument("--force", action="store_true", help="Re-run all steps even if already done.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output.")
    parser.add_argument("--resume", action="store_true", help="Resume after a reboot (called by startup task).")
    parser.add_argument("--config", type=Path, default=None, metavar="FILE", help="Path to custom config YAML.")
    parser.add_argument("--skip-rocm", action="store_true", help="Skip ROCm/HIP update step.")
    parser.add_argument("--skip-llama", action="store_true", help="Skip llama.cpp build step.")
    return parser


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    def __init__(self, cfg: GASUConfig, resume: bool = False, skip_rocm: bool = False, skip_llama: bool = False) -> None:
        self.cfg = cfg
        self.resume = resume
        self.skip_rocm = skip_rocm
        self.skip_llama = skip_llama

        state_dir = Path(cfg.paths.state_dir)
        self.state = StateManager(state_dir)
        self.intel = VersionIntel()
        self.gpu = GPUDetector()
        self.manifest: UpdateManifest | None = None
        self.updates_applied: list[tuple[str, str, str]] = []

    def run(self) -> int:
        """Execute the main state machine. Returns exit code."""
        run_id = str(uuid.uuid4())[:8]
        self.state.start_run(run_id)

        try:
            # Handle reboot resume
            if self.resume or self.state.has_pending_reboot():
                return self._handle_resume()

            # Phase 1: check versions
            if not self._step_check_versions():
                return 1

            if not self.manifest or not self.manifest.any_updates:
                print_success("Everything is up to date. Nothing to do.")
                self.state.finish_run(success=True)
                return 0

            # Confirm before proceeding
            if not self.cfg.behavior.dry_run:
                if not confirm(
                    "Updates are available. Proceed with installation?",
                    default=True,
                    auto_yes=self.cfg.behavior.auto_yes,
                ):
                    print_info("Update cancelled by user.")
                    self.state.finish_run(success=True)
                    return 0

            # Phase 2: GPU detection
            gpu_targets = self._detect_gpu_targets()

            # Phase 3: ROCm/HIP update
            if not self.skip_rocm and self.manifest.rocm.needs_update:
                reboot_required = self._step_update_rocm()
                if reboot_required:
                    return self._initiate_reboot("post_rocm_resume")

            # Phase 4: llama.cpp build
            if not self.skip_llama and self.manifest.llama_cpp.needs_update:
                self._step_build_llama(gpu_targets)

            # Phase 5: validate
            self._step_validate()

            # Summary
            print_summary(self.updates_applied, dry_run=self.cfg.behavior.dry_run)
            self.state.finish_run(success=True)
            return 0

        except KeyboardInterrupt:
            print_warning("\nInterrupted by user.")
            self.state.finish_run(success=False)
            return 130
        except Exception as exc:
            print_error(f"Fatal error: {exc}")
            logger.exception("Unhandled exception in orchestrator")
            self.state.finish_run(success=False)
            return 1
        finally:
            self.state.close()

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _step_check_versions(self) -> bool:
        step_id = "check_versions"
        if self.state.is_done(step_id) and not self.cfg.behavior.force:
            print_info("Version check already completed — skipping.")
            return True

        print_phase("Version Check")
        self.state.mark_running(step_id)
        print_step("Querying installed versions and upstream releases...")

        try:
            self.manifest = self.intel.check_all()
        except Exception as exc:
            print_error(f"Version check failed: {exc}")
            self.state.mark_failed(step_id, str(exc))
            return False

        # Display table
        rows = [
            (
                self.manifest.rocm.name,
                self.manifest.rocm.installed,
                self.manifest.rocm.latest,
                self.manifest.rocm.needs_update,
            ),
            (
                self.manifest.llama_cpp.name,
                self.manifest.llama_cpp.installed,
                self.manifest.llama_cpp.latest,
                self.manifest.llama_cpp.needs_update,
            ),
        ]
        print_version_table(rows)

        if self.manifest.rocm.error:
            print_warning(f"ROCm version check warning: {self.manifest.rocm.error}")
        if self.manifest.llama_cpp.error:
            print_warning(f"llama.cpp version check warning: {self.manifest.llama_cpp.error}")

        self.state.mark_done(step_id)
        return True

    def _detect_gpu_targets(self) -> list[str]:
        step_id = "gpu_detect"
        print_phase("GPU Detection")
        self.state.mark_running(step_id)

        if self.cfg.gpu.auto_detect:
            print_step("Auto-detecting GPU architecture...")
            targets = self.gpu.detect()
            print_info(f"Detected GPU targets: {', '.join(targets)}")
        else:
            targets = self.cfg.gpu.targets
            print_info(f"Using configured GPU targets: {', '.join(targets)}")

        self.state.mark_done(step_id, output=",".join(targets))
        return targets

    def _step_update_rocm(self) -> bool:
        """Returns True if a reboot is required."""
        step_id = "update_rocm"
        if self.state.is_done(step_id) and not self.cfg.behavior.force:
            print_info("ROCm update already completed — skipping.")
            return False

        print_phase("ROCm/HIP Update")
        self.state.mark_running(step_id)

        old_version = self.manifest.rocm.installed if self.manifest else None
        new_version = self.manifest.rocm.latest if self.manifest else None

        reboot_required = False

        if self.cfg.behavior.dry_run:
            from src.cli import print_dry_run
            print_dry_run(f"Would update ROCm/HIP from {old_version} → {new_version}")
            self.state.mark_done(step_id, output="dry-run")
            self.updates_applied.append(("ROCm/HIP", old_version or "—", new_version or "—"))
            return False

        if sys.platform == "linux":
            from src.linux.rocm_updater import ROCmUpdater
            updater = ROCmUpdater(self.cfg)
            reboot_required = updater.update()
        elif sys.platform == "win32":
            from src.windows.hip_updater import HIPUpdater
            updater = HIPUpdater(self.cfg)
            reboot_required = updater.update()
        else:
            print_warning(f"Unsupported OS: {sys.platform}. Skipping ROCm update.")
            self.state.mark_skipped(step_id, "unsupported OS")
            return False

        self.state.mark_done(step_id, output=f"updated to {new_version}")
        self.updates_applied.append(("ROCm/HIP", old_version or "—", new_version or "—"))
        return reboot_required

    def _step_build_llama(self, gpu_targets: list[str]) -> None:
        step_id = "build_llama"
        if self.state.is_done(step_id) and not self.cfg.behavior.force:
            print_info("llama.cpp build already completed — skipping.")
            return

        print_phase("llama.cpp Build")
        self.state.mark_running(step_id)

        old_version = self.manifest.llama_cpp.installed if self.manifest else None
        new_version = self.manifest.llama_cpp.latest if self.manifest else None

        if self.cfg.behavior.dry_run:
            from src.cli import print_dry_run
            print_dry_run(f"Would build llama.cpp {new_version} with targets: {', '.join(gpu_targets)}")
            self.state.mark_done(step_id, output="dry-run")
            self.updates_applied.append(("llama.cpp", old_version or "—", new_version or "—"))
            return

        if sys.platform == "linux":
            from src.linux.llama_builder import LlamaBuilderLinux
            builder = LlamaBuilderLinux(self.cfg, gpu_targets)
            builder.build_and_install()
        elif sys.platform == "win32":
            from src.windows.llama_builder import LlamaBuilderWindows
            builder = LlamaBuilderWindows(self.cfg, gpu_targets)
            builder.build_and_install()
        else:
            print_warning(f"Unsupported OS: {sys.platform}. Skipping llama.cpp build.")
            self.state.mark_skipped(step_id, "unsupported OS")
            return

        self.state.mark_done(step_id, output=f"built {new_version}")
        self.updates_applied.append(("llama.cpp", old_version or "—", new_version or "—"))

    def _step_validate(self) -> None:
        step_id = "validate"
        print_phase("Validation")
        self.state.mark_running(step_id)

        validation_passed = True
        if self.cfg.behavior.dry_run:
            from src.cli import print_dry_run
            print_dry_run("Would run: rocminfo, hipcc --version, llama-cli --version")
            self.state.mark_done(step_id, output="dry-run")
            return

        # Run health checks
        checks = _build_health_checks()
        for name, cmd, required in checks:
            result = _run_check(cmd)
            if result:
                print_success(f"✔ {name}: {result[:60]}")
            elif required:
                print_warning(f"⚠ {name}: not found or failed (may be expected)")
                validation_passed = False
            else:
                print_step(f"  {name}: not available (optional)")

        if validation_passed:
            self.state.mark_done(step_id, output="all checks passed")
        else:
            self.state.mark_done(step_id, output="some optional checks failed")

    # ------------------------------------------------------------------
    # Reboot handling
    # ------------------------------------------------------------------

    def _initiate_reboot(self, resume_step: str) -> int:
        from src.cli import reboot_countdown

        print_phase("System Reboot Required")
        print_warning("A reboot is required to complete driver installation.")

        self.state.write_reboot_handoff(resume_step)

        if sys.platform == "linux":
            from src.linux.reboot_handler import RebootHandler
            handler = RebootHandler(self.cfg)
        elif sys.platform == "win32":
            from src.windows.reboot_handler import RebootHandler
            handler = RebootHandler(self.cfg)
        else:
            print_warning("Unknown OS — cannot register resume task.")
            return 1

        # Register the resume-on-boot task
        if not self.cfg.behavior.dry_run:
            handler.register_resume_task()
            print_success("Resume task registered. Rebooting will continue the update automatically.")

        should_reboot = reboot_countdown(
            self.cfg.behavior.reboot_countdown_seconds,
            auto_reboot=self.cfg.behavior.auto_reboot,
        )

        if should_reboot and not self.cfg.behavior.dry_run:
            handler.reboot()

        self.state.finish_run(success=True)
        return 0

    def _handle_resume(self) -> int:
        print_phase("Resuming After Reboot")
        handoff = self.state.read_reboot_handoff()
        if not handoff:
            print_warning("No reboot handoff found. Running fresh check...")
            return self._full_run_after_reboot()

        print_info(f"Resuming from step: {handoff.resume_step}")
        self.state.clear_reboot_handoff()

        # Validate ROCm post-reboot
        print_phase("Post-Reboot Validation")
        if not self._post_reboot_validate():
            print_error("Post-reboot validation failed. Please check ROCm installation manually.")
            return 1

        # Continue with llama.cpp if not done
        if not self.state.is_done("check_versions"):
            self._step_check_versions()

        if self.manifest and self.manifest.llama_cpp.needs_update and not self.skip_llama:
            gpu_targets = self._detect_gpu_targets()
            self._step_build_llama(gpu_targets)

        self._step_validate()
        print_summary(self.updates_applied)

        # Clean up resume task
        if sys.platform == "linux":
            from src.linux.reboot_handler import RebootHandler
            RebootHandler(self.cfg).unregister_resume_task()
        elif sys.platform == "win32":
            from src.windows.reboot_handler import RebootHandler
            RebootHandler(self.cfg).unregister_resume_task()

        self.state.finish_run(success=True)
        return 0

    def _full_run_after_reboot(self) -> int:
        """Called when resuming but no handoff found — treat as fresh run."""
        if not self._step_check_versions():
            return 1
        if self.manifest and self.manifest.any_updates:
            gpu_targets = self._detect_gpu_targets()
            if self.manifest.llama_cpp.needs_update and not self.skip_llama:
                self._step_build_llama(gpu_targets)
        self._step_validate()
        print_summary(self.updates_applied)
        self.state.finish_run(success=True)
        return 0

    def _post_reboot_validate(self) -> bool:
        """Quick sanity check that ROCm is loaded after reboot."""
        import subprocess
        for cmd in (["rocm-smi", "--version"], ["hipcc", "--version"]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print_success(f"{cmd[0]} present: {result.stdout.strip()[:60]}")
                    return True
            except FileNotFoundError:
                continue
        return False


# ---------------------------------------------------------------------------
# Health check helpers
# ---------------------------------------------------------------------------


def _build_health_checks() -> list[tuple[str, list[str], bool]]:
    """List of (display_name, command, is_required) tuples."""
    return [
        ("rocm-smi",    ["rocm-smi", "--version"],   False),
        ("hipcc",       ["hipcc", "--version"],       False),
        ("rocminfo",    ["rocminfo"],                 False),
        ("llama-cli",   ["llama-cli", "--version"],   False),
        ("llama-server",["llama-server", "--version"],False),
    ]


def _run_check(cmd: list[str]) -> str | None:
    import subprocess
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return (result.stdout + result.stderr).strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    cfg = load_config(
        config_path=args.config,
        dry_run=args.dry_run,
        auto_yes=args.auto_yes,
        force=args.force,
        verbose=args.verbose,
    )

    # Configure logging
    log_level = logging.DEBUG if cfg.behavior.verbose else getattr(logging, cfg.log_level, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print_banner(dry_run=cfg.behavior.dry_run)

    # Privilege check (skip in dry-run mode — not needed)
    if not cfg.behavior.dry_run:
        ensure_admin()
    else:
        if not is_admin():
            from src.cli import print_warning as _warn
            _warn("Running without admin — dry-run only, no changes will be made.")

    orchestrator = Orchestrator(
        cfg=cfg,
        resume=args.resume,
        skip_rocm=args.skip_rocm,
        skip_llama=args.skip_llama,
    )
    sys.exit(orchestrator.run())


if __name__ == "__main__":
    main()
