from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..paths import default_review_db_path


@dataclass(slots=True)
class ReviewDraftSnapshot:
    task_id: str
    version: int
    state: dict[str, Any]
    updated_at: datetime


class ReviewDraftConflictError(RuntimeError):
    def __init__(self, current: ReviewDraftSnapshot | None) -> None:
        super().__init__("Review draft version conflict")
        self.current = current


class SQLiteReviewDraftRepository:
    """Versioned workbench drafts stored beside durable review tasks."""

    def __init__(self, db_path: str | None = None, *, history_limit: int = 30) -> None:
        self._db_path = db_path or str(default_review_db_path())
        self._history_limit = max(5, min(int(history_limit), 100))
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_workbench_drafts (
                    task_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_workbench_draft_versions (
                    task_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_review_workbench_draft_versions_task
                ON review_workbench_draft_versions(task_id, version DESC)
                """
            )

    def get(self, task_id: str) -> ReviewDraftSnapshot | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT task_id, version, state_json, updated_at FROM review_workbench_drafts WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _row_to_snapshot(row) if row else None

    def save(self, task_id: str, base_version: int, state: dict[str, Any]) -> ReviewDraftSnapshot:
        now = datetime.now(UTC)
        serialized = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT task_id, version, state_json, updated_at FROM review_workbench_drafts WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            current = _row_to_snapshot(row) if row else None
            current_version = current.version if current else 0
            if current_version != base_version:
                raise ReviewDraftConflictError(current)

            version = current_version + 1
            timestamp = _dt_to_text(now)
            conn.execute(
                """
                INSERT INTO review_workbench_drafts(task_id, version, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    version = excluded.version,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (task_id, version, serialized, timestamp),
            )
            conn.execute(
                """
                INSERT INTO review_workbench_draft_versions(task_id, version, state_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, version, serialized, timestamp),
            )
            conn.execute(
                """
                DELETE FROM review_workbench_draft_versions
                WHERE task_id = ? AND version NOT IN (
                    SELECT version FROM review_workbench_draft_versions
                    WHERE task_id = ? ORDER BY version DESC LIMIT ?
                )
                """,
                (task_id, task_id, self._history_limit),
            )
        return ReviewDraftSnapshot(task_id=task_id, version=version, state=state, updated_at=now)

    def list_versions(self, task_id: str, limit: int = 20) -> list[ReviewDraftSnapshot]:
        bounded_limit = max(1, min(int(limit), self._history_limit))
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT task_id, version, state_json, created_at AS updated_at
                FROM review_workbench_draft_versions
                WHERE task_id = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (task_id, bounded_limit),
            ).fetchall()
        return [_row_to_snapshot(row) for row in rows]

    def restore(self, task_id: str, version: int, base_version: int) -> ReviewDraftSnapshot | None:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT task_id, version, state_json, created_at AS updated_at
                FROM review_workbench_draft_versions
                WHERE task_id = ? AND version = ?
                """,
                (task_id, version),
            ).fetchone()
        if row is None:
            return None
        historical = _row_to_snapshot(row)
        return self.save(task_id, base_version, historical.state)

    def delete(self, task_id: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM review_workbench_draft_versions WHERE task_id = ?", (task_id,))
            conn.execute("DELETE FROM review_workbench_drafts WHERE task_id = ?", (task_id,))


def _dt_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _dt_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_to_snapshot(row: sqlite3.Row) -> ReviewDraftSnapshot:
    try:
        parsed = json.loads(str(row["state_json"]))
        state = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        state = {}
    return ReviewDraftSnapshot(
        task_id=str(row["task_id"]),
        version=int(row["version"]),
        state=state,
        updated_at=_dt_from_text(str(row["updated_at"])),
    )
