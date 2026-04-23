"""
test_state_manager.py — Tests for the SQLite checkpoint state manager.

Verifies:
- Run lifecycle (start, finish)
- Step CRUD (mark_running, mark_done, mark_failed, mark_skipped)
- is_done idempotency
- Reboot handoff write/read/clear
- Persistence across manager instances (same DB path)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.state_manager import StateManager, StepStatus, RebootHandoff


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def sm(tmp_state_dir: Path) -> StateManager:
    manager = StateManager(tmp_state_dir)
    manager.start_run("test-run-001")
    return manager


# ---------------------------------------------------------------------------
# Run management
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    def test_start_run_creates_record(self, sm: StateManager):
        # run_id is set
        assert sm.run_id == "test-run-001"

    def test_finish_run_success(self, sm: StateManager, tmp_state_dir: Path):
        sm.finish_run(success=True)
        last_run = json.loads((tmp_state_dir / "last_run.json").read_text())
        assert last_run["success"] is True

    def test_finish_run_failure(self, sm: StateManager, tmp_state_dir: Path):
        sm.finish_run(success=False)
        last_run = json.loads((tmp_state_dir / "last_run.json").read_text())
        assert last_run["success"] is False

    def test_duplicate_run_id_is_idempotent(self, tmp_state_dir: Path):
        sm1 = StateManager(tmp_state_dir)
        sm1.start_run("same-run")
        sm1.mark_done("step-a")
        sm1.close()

        sm2 = StateManager(tmp_state_dir)
        sm2.start_run("same-run")  # same ID — should not error
        assert sm2.is_done("step-a")
        sm2.close()


# ---------------------------------------------------------------------------
# Step management
# ---------------------------------------------------------------------------


class TestStepManagement:
    def test_mark_running(self, sm: StateManager):
        sm.mark_running("check_versions")
        record = sm.get_step("check_versions")
        assert record is not None
        assert record.status == StepStatus.RUNNING

    def test_mark_done(self, sm: StateManager):
        sm.mark_running("check_versions")
        sm.mark_done("check_versions", output="6.3.1")
        record = sm.get_step("check_versions")
        assert record.status == StepStatus.DONE
        assert record.output == "6.3.1"

    def test_mark_failed(self, sm: StateManager):
        sm.mark_running("update_rocm")
        sm.mark_failed("update_rocm", error="download 404")
        record = sm.get_step("update_rocm")
        assert record.status == StepStatus.FAILED
        assert record.error == "download 404"

    def test_mark_skipped(self, sm: StateManager):
        sm.mark_skipped("build_llama", reason="no update needed")
        record = sm.get_step("build_llama")
        assert record.status == StepStatus.SKIPPED

    def test_is_done_false_before_completion(self, sm: StateManager):
        sm.mark_running("check_versions")
        assert sm.is_done("check_versions") is False

    def test_is_done_true_after_done(self, sm: StateManager):
        sm.mark_running("check_versions")
        sm.mark_done("check_versions")
        assert sm.is_done("check_versions") is True

    def test_is_done_false_for_unknown_step(self, sm: StateManager):
        assert sm.is_done("nonexistent_step") is False

    def test_get_all_steps_order(self, sm: StateManager):
        for step in ("check_versions", "gpu_detect", "update_rocm"):
            sm.mark_done(step)
        steps = sm.get_all_steps()
        names = [s.step_id for s in steps]
        assert names == ["check_versions", "gpu_detect", "update_rocm"]

    def test_get_nonexistent_step_returns_none(self, sm: StateManager):
        assert sm.get_step("does_not_exist") is None


# ---------------------------------------------------------------------------
# Reboot handoff
# ---------------------------------------------------------------------------


class TestRebootHandoff:
    def test_write_and_read_handoff(self, sm: StateManager):
        sm.write_reboot_handoff("post_rocm_resume", {"gpu": "gfx1100"})
        handoff = sm.read_reboot_handoff()
        assert handoff is not None
        assert handoff.resume_step == "post_rocm_resume"
        assert handoff.extra.get("gpu") == "gfx1100"
        assert handoff.run_id == sm.run_id

    def test_has_pending_reboot_true(self, sm: StateManager):
        sm.write_reboot_handoff("post_rocm_resume")
        assert sm.has_pending_reboot() is True

    def test_has_pending_reboot_false_initially(self, sm: StateManager):
        assert sm.has_pending_reboot() is False

    def test_clear_handoff(self, sm: StateManager):
        sm.write_reboot_handoff("post_rocm_resume")
        sm.clear_reboot_handoff()
        assert sm.has_pending_reboot() is False
        assert sm.read_reboot_handoff() is None

    def test_clear_handoff_when_not_exists(self, sm: StateManager):
        """Clearing when no handoff exists should not raise."""
        sm.clear_reboot_handoff()  # should be a no-op


# ---------------------------------------------------------------------------
# Persistence across instances
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_steps_persist_across_instances(self, tmp_state_dir: Path):
        sm1 = StateManager(tmp_state_dir)
        sm1.start_run("persistent-run")
        sm1.mark_done("step_one", output="done")
        sm1.close()

        sm2 = StateManager(tmp_state_dir)
        sm2.start_run("persistent-run")
        assert sm2.is_done("step_one") is True
        record = sm2.get_step("step_one")
        assert record.output == "done"
        sm2.close()
