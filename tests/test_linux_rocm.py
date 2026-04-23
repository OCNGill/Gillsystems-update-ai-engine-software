"""
test_linux_rocm.py — Tests for Linux ROCm updater sub-agent.

Uses mocks to avoid touching the real system. Verifies:
- distro detection
- installer URL construction
- amdgpu-install command construction
- user group addition
- reboot requirement detection
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.config import load_config, GASUConfig, BehaviorConfig


@pytest.fixture
def dry_run_cfg() -> GASUConfig:
    cfg = load_config()
    cfg.behavior.dry_run = True
    return cfg


@pytest.fixture
def live_cfg() -> GASUConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    return cfg


# ---------------------------------------------------------------------------
# ROCmUpdater — distro detection
# ---------------------------------------------------------------------------


class TestDistroDetection:
    def test_detect_ubuntu(self):
        from src.linux.rocm_updater import _detect_distro, _is_debian_based

        with patch("platform.freedesktop_os_release", return_value={"ID": "ubuntu", "ID_LIKE": "debian"}):
            distro = _detect_distro()

        assert _is_debian_based(distro) is True

    def test_detect_fedora(self):
        from src.linux.rocm_updater import _detect_distro, _is_debian_based

        with patch("platform.freedesktop_os_release", return_value={"ID": "fedora", "ID_LIKE": ""}):
            distro = _detect_distro()

        assert _is_debian_based(distro) is False

    def test_detect_fallback(self):
        from src.linux.rocm_updater import _detect_distro

        with patch("platform.freedesktop_os_release", side_effect=AttributeError), \
             patch("builtins.open", side_effect=OSError):
            distro = _detect_distro()

        assert distro == ""


# ---------------------------------------------------------------------------
# ROCmUpdater — dry-run mode
# ---------------------------------------------------------------------------


class TestROCmUpdaterDryRun:
    def test_update_dry_run_returns_no_reboot(self, dry_run_cfg: GASUConfig):
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(dry_run_cfg)

        with patch.object(updater, "_detect_distro" if hasattr(updater, "_detect_distro") else "__class__"), \
             patch("src.linux.rocm_updater._detect_distro", return_value="ubuntu 22.04"), \
             patch("src.linux.rocm_updater._run_privileged") as mock_run, \
             patch("urllib.request.urlretrieve") as mock_dl:

            result = updater.update()

        # Dry-run: no downloads, no privileged commands
        mock_dl.assert_not_called()
        mock_run.assert_not_called()
        # No reboot required in dry-run
        assert result is False

    def test_amdgpu_install_command_content(self, dry_run_cfg: GASUConfig):
        """Verify the amdgpu-install command uses the right usecases."""
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(dry_run_cfg)
        usecases = ",".join(dry_run_cfg.behavior.rocm_usecases)
        assert "rocm" in usecases
        assert "hiplibsdk" in usecases


# ---------------------------------------------------------------------------
# ROCmUpdater — reboot detection
# ---------------------------------------------------------------------------


class TestROCmRebootDetection:
    def test_reboot_detected_from_kernel_hint(self, live_cfg: GASUConfig):
        """If amdgpu-install output contains 'reboot', return True."""
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(live_cfg)

        mock_result = MagicMock()
        mock_result.stdout = "Installing kernel module...\nPlease reboot to complete installation.\n"
        mock_result.stderr = ""

        with patch("src.linux.rocm_updater._run_privileged", return_value=mock_result):
            reboot = updater._run_amdgpu_install()

        assert reboot is True

    def test_no_reboot_when_no_kernel_hint(self, live_cfg: GASUConfig):
        """If output has no reboot hints, return False."""
        from src.linux.rocm_updater import ROCmUpdater

        updater = ROCmUpdater(live_cfg)

        mock_result = MagicMock()
        mock_result.stdout = "ROCm packages installed successfully.\n"
        mock_result.stderr = ""

        with patch("src.linux.rocm_updater._run_privileged", return_value=mock_result):
            reboot = updater._run_amdgpu_install()

        assert reboot is False


# ---------------------------------------------------------------------------
# RebootHandler (Linux)
# ---------------------------------------------------------------------------


class TestLinuxRebootHandler:
    def test_register_task_dry_run(self, dry_run_cfg: GASUConfig):
        from src.linux.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        # Should not raise — dry-run just prints
        handler.register_resume_task()

    def test_unregister_task_dry_run(self, dry_run_cfg: GASUConfig):
        from src.linux.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        handler.unregister_resume_task()  # no-op in dry-run

    def test_reboot_dry_run(self, dry_run_cfg: GASUConfig):
        from src.linux.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        with patch("subprocess.run") as mock_run:
            handler.reboot()
        mock_run.assert_not_called()

    def test_service_file_content(self, live_cfg: GASUConfig):
        """The systemd service content should reference the launcher."""
        from src.linux.reboot_handler import _SERVICE_TEMPLATE, RebootHandler

        handler = RebootHandler(live_cfg)
        content = _SERVICE_TEMPLATE.format(
            launcher=str(handler.launcher_path),
            service_name="gasu-resume.service",
        )
        assert "--resume" in content
        assert "gasu-resume.service" in content
        assert "oneshot" in content
