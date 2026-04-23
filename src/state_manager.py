"""
state_manager.py — SQLite-backed checkpoint ledger for GASU.

Each step is idempotent. On startup the orchestrator checks for an incomplete
run and resumes from the last successful step. A JSON handoff file is written
before any OS reboot so the resume‑task can reload context.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enumerations & models
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepRecord(BaseModel):
    step_id: str
    status: StepStatus
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class RebootHandoff(BaseModel):
    """Written to disk before an OS reboot so the resume task can restore context."""
    resume_step: str
    run_id: str
    timestamp: str
    extra: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# State manager
# ---------------------------------------------------------------------------


class StateManager:
    """
    Manages agent progress via an SQLite database and a JSON handoff file.

    Tables
    ------
    steps : one row per idempotent step
    runs  : one row per agent invocation (run)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS runs (
        run_id      TEXT PRIMARY KEY,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        status      TEXT NOT NULL DEFAULT 'running'
    );

    CREATE TABLE IF NOT EXISTS steps (
        step_id      TEXT NOT NULL,
        run_id       TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'pending',
        started_at   TEXT,
        completed_at TEXT,
        output       TEXT,
        error        TEXT,
        metadata     TEXT,
        PRIMARY KEY (step_id, run_id),
        FOREIGN KEY (run_id) REFERENCES runs(run_id)
    );
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.state_dir / "checkpoint.db"
        self.handoff_path = self.state_dir / "reboot_handoff.json"
        self.last_run_path = self.state_dir / "last_run.json"

        self._conn: Optional[sqlite3.Connection] = None
        self._run_id: Optional[str] = None

        self._init_db()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Run management
    # ------------------------------------------------------------------

    def start_run(self, run_id: str) -> None:
        """Begin a new agent invocation run."""
        self._run_id = run_id
        now = _utcnow()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO runs (run_id, started_at, status) VALUES (?, ?, 'running')",
                (run_id, now),
            )

    def finish_run(self, success: bool = True) -> None:
        """Mark the current run as finished."""
        if not self._run_id:
            return
        status = "done" if success else "failed"
        now = _utcnow()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ?, status = ? WHERE run_id = ?",
                (now, status, self._run_id),
            )
        self._write_last_run(success)

    def _write_last_run(self, success: bool) -> None:
        steps = self.get_all_steps()
        summary = {
            "run_id": self._run_id,
            "success": success,
            "timestamp": _utcnow(),
            "steps": [s.model_dump() for s in steps],
        }
        self.last_run_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> str:
        if not self._run_id:
            raise RuntimeError("No active run. Call start_run() first.")
        return self._run_id

    def upsert_step(self, step_id: str, status: StepStatus, **kwargs: Any) -> None:
        """Create or update a step record."""
        now = _utcnow()
        metadata = json.dumps(kwargs.pop("metadata", None))
        output = kwargs.get("output")
        error = kwargs.get("error")

        started_at = now if status == StepStatus.RUNNING else None
        completed_at = now if status in (StepStatus.DONE, StepStatus.FAILED, StepStatus.SKIPPED) else None

        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT step_id FROM steps WHERE step_id = ? AND run_id = ?",
                (step_id, self.run_id),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE steps SET status=?, started_at=COALESCE(started_at, ?),
                       completed_at=?, output=?, error=?, metadata=?
                       WHERE step_id=? AND run_id=?""",
                    (
                        status.value,
                        started_at,
                        completed_at,
                        output,
                        error,
                        metadata,
                        step_id,
                        self.run_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO steps
                       (step_id, run_id, status, started_at, completed_at, output, error, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        step_id,
                        self.run_id,
                        status.value,
                        started_at,
                        completed_at,
                        output,
                        error,
                        metadata,
                    ),
                )

    def mark_running(self, step_id: str) -> None:
        self.upsert_step(step_id, StepStatus.RUNNING)

    def mark_done(self, step_id: str, output: str = "") -> None:
        self.upsert_step(step_id, StepStatus.DONE, output=output)

    def mark_failed(self, step_id: str, error: str = "") -> None:
        self.upsert_step(step_id, StepStatus.FAILED, error=error)

    def mark_skipped(self, step_id: str, reason: str = "") -> None:
        self.upsert_step(step_id, StepStatus.SKIPPED, output=reason)

    def get_step(self, step_id: str) -> Optional[StepRecord]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM steps WHERE step_id = ? AND run_id = ?",
                (step_id, self.run_id),
            ).fetchone()
        if not row:
            return None
        return _row_to_step(row)

    def is_done(self, step_id: str) -> bool:
        record = self.get_step(step_id)
        return record is not None and record.status == StepStatus.DONE

    def get_all_steps(self) -> List[StepRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY rowid",
                (self.run_id,),
            ).fetchall()
        return [_row_to_step(r) for r in rows]

    # ------------------------------------------------------------------
    # Reboot handoff
    # ------------------------------------------------------------------

    def write_reboot_handoff(self, resume_step: str, extra: Dict[str, Any] | None = None) -> None:
        """Persist the handoff file before a system reboot."""
        handoff = RebootHandoff(
            resume_step=resume_step,
            run_id=self.run_id,
            timestamp=_utcnow(),
            extra=extra or {},
        )
        self.handoff_path.write_text(
            handoff.model_dump_json(indent=2), encoding="utf-8"
        )

    def read_reboot_handoff(self) -> Optional[RebootHandoff]:
        """Load the handoff file if it exists."""
        if not self.handoff_path.exists():
            return None
        data = json.loads(self.handoff_path.read_text(encoding="utf-8"))
        return RebootHandoff.model_validate(data)

    def clear_reboot_handoff(self) -> None:
        """Remove the handoff file once resume is complete."""
        if self.handoff_path.exists():
            self.handoff_path.unlink()

    def has_pending_reboot(self) -> bool:
        return self.handoff_path.exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_step(row: sqlite3.Row) -> StepRecord:
    meta_raw = row["metadata"]
    meta = json.loads(meta_raw) if meta_raw else None
    return StepRecord(
        step_id=row["step_id"],
        status=StepStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        output=row["output"],
        error=row["error"],
        metadata=meta,
    )
