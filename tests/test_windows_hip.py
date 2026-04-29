"""
test_windows_hip.py — Tests for Windows HIP SDK updater sub-agent.

Uses mocks to avoid any real downloads or registry writes.
Tests are designed to run on both Windows and Linux (CI).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.config import load_config, GillsystemsAIStackUpdaterConfig


@pytest.fixture
def dry_run_cfg() -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = True
    return cfg


@pytest.fixture
def live_cfg() -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    return cfg


# ---------------------------------------------------------------------------
# HIPUpdater — finder
# ---------------------------------------------------------------------------


class TestHIPUpdaterFinder:
    def test_find_latest_returns_url_and_version(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        """Verify that the latest installer URL resolves to a plausible AMD URL."""
        pytest.importorskip("httpx")

        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(dry_run_cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.head.return_value = mock_response
            mock_client_cls.return_value = mock_client

            url, version = updater._find_latest_installer()

        assert url is not None
        assert "HIP-SDK-Installer" in url
        assert version is not None

    def test_find_latest_falls_back_gracefully(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        """When HTTP fails, it falls back to hardcoded URL."""
        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(dry_run_cfg)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.head.side_effect = Exception("network error")
            mock_client_cls.return_value = mock_client

            url, version = updater._find_latest_installer()

        # Should still return a fallback
        assert url is not None
        assert "HIP-SDK-Installer" in url


# ---------------------------------------------------------------------------
# HIPUpdater — dry-run mode
# ---------------------------------------------------------------------------


class TestHIPUpdaterDryRun:
    def test_update_dry_run_no_downloads(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(dry_run_cfg)

        # Mock _find_latest_installer to avoid HTTP
        with patch.object(
            updater, "_find_latest_installer",
            return_value=("https://example.com/HIP-SDK-Installer-6.3.1.0.exe", "6.3.1")
        ), patch("urllib.request.urlretrieve") as mock_dl, \
           patch("subprocess.run") as mock_run:
            result = updater.update()

        mock_dl.assert_not_called()
        # No real subprocess calls in dry-run
        assert result is False

    def test_run_silent_install_dry_run_returns_false(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(dry_run_cfg)
        result = updater._run_silent_install(
            Path(r"C:\Temp\HIP-SDK-Installer-6.3.1.0.exe"),
            "6.3.1",
        )
        assert result is False


# ---------------------------------------------------------------------------
# HIPUpdater — exit code handling
# ---------------------------------------------------------------------------


class TestHIPSilentInstall:
    def test_exit_code_0_no_reboot(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(live_cfg)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = updater._run_silent_install(
                Path(r"C:\Temp\HIP-SDK-Installer.exe"), "6.3.1"
            )

        assert result is False

    def test_exit_code_3010_requires_reboot(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        """Exit code 3010 is MSI's 'success, reboot required' convention."""
        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(live_cfg)

        mock_result = MagicMock()
        mock_result.returncode = 3010

        with patch("subprocess.run", return_value=mock_result):
            result = updater._run_silent_install(
                Path(r"C:\Temp\HIP-SDK-Installer.exe"), "6.3.1"
            )

        assert result is True

    def test_exit_code_nonzero_raises(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.hip_updater import HIPUpdater

        updater = HIPUpdater(live_cfg)

        mock_result = MagicMock()
        mock_result.returncode = 1603  # generic MSI failure

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="installer exited with code"):
                updater._run_silent_install(
                    Path(r"C:\Temp\HIP-SDK-Installer.exe"), "6.3.1"
                )


# ---------------------------------------------------------------------------
# RebootHandler (Windows)
# ---------------------------------------------------------------------------


class TestWindowsRebootHandler:
    def test_register_task_dry_run(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        # Should not call schtasks in dry-run
        with patch("subprocess.run") as mock_run:
            handler.register_resume_task()
        mock_run.assert_not_called()

    def test_unregister_task_dry_run(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        with patch("subprocess.run") as mock_run:
            handler.unregister_resume_task()
        mock_run.assert_not_called()

    def test_reboot_dry_run(self, dry_run_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.reboot_handler import RebootHandler

        handler = RebootHandler(dry_run_cfg)
        with patch("subprocess.run") as mock_run:
            handler.reboot()
        mock_run.assert_not_called()

    def test_register_task_live_calls_schtasks(self, live_cfg: GillsystemsAIStackUpdaterConfig):
        from src.windows.reboot_handler import RebootHandler, _TASK_NAME

        handler = RebootHandler(live_cfg)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            handler.register_resume_task()

        # Verify schtasks was called with the right flags
        args = mock_run.call_args[0][0]
        assert "schtasks" in args
        assert "/create" in args
        assert _TASK_NAME in args
        assert "--resume" in " ".join(args)
