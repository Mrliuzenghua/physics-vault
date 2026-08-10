"""SQLite persistence with atomic claim semantics for confirmed operation plans."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_contracts.src.operation_plan import OperationPlan

from ..database import connect_db
from ..db_schema import initialize_database


@dataclass(frozen=True, slots=True)
class StoredOperationPlan:
    plan: OperationPlan
    status: str
    result: Any | None
    error: str | None


class OperationPlanRepository:
    """Store previews and atomically transition them from planned to executing."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else None
        if self._db_path is not None:
            initialize_database(self._db_path)

    def save(self, plan: OperationPlan) -> StoredOperationPlan:
        now = _utc_now()
        payload = plan.model_dump(mode="json")
        with _transaction(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO operation_plans
                (operation_id, plan_json, expected_version, status, expires_at, created_at, updated_at)
                VALUES (?, ?, ?, 'planned', ?, ?, ?)
                """,
                (plan.operation_id, json.dumps(payload, ensure_ascii=False), plan.expected_version, plan.expires_at.isoformat(), now, now),
            )
            return _row_to_stored(_fetch(conn, plan.operation_id))

    def get(self, operation_id: str) -> StoredOperationPlan | None:
        with connect_db(self._db_path, writable=False) as conn:
            row = _fetch(conn, operation_id)
        return _row_to_stored(row) if row is not None else None

    def claim(self, operation_id: str, *, now: datetime) -> tuple[StoredOperationPlan, bool] | None:
        """Claim once with BEGIN IMMEDIATE so only one process can execute a plan."""
        with _transaction(self._db_path) as conn:
            row = _fetch(conn, operation_id)
            if row is None:
                return None
            stored = _row_to_stored(row)
            if stored.status != "planned":
                return stored, False
            if stored.plan.expires_at <= now:
                conn.execute(
                    "UPDATE operation_plans SET status='expired', updated_at=? WHERE operation_id=? AND status='planned'",
                    (_iso(now), operation_id),
                )
                return _row_to_stored(_fetch(conn, operation_id)), False
            updated = conn.execute(
                """
                UPDATE operation_plans
                SET status='executing', started_at=?, updated_at=?
                WHERE operation_id=? AND status='planned'
                """,
                (_iso(now), _iso(now), operation_id),
            )
            return _row_to_stored(_fetch(conn, operation_id)), updated.rowcount == 1

    def complete(self, operation_id: str, result: Any, *, now: datetime) -> StoredOperationPlan:
        with _transaction(self._db_path) as conn:
            conn.execute(
                """
                UPDATE operation_plans
                SET status='completed', result_json=?, error=NULL, finished_at=?, updated_at=?
                WHERE operation_id=? AND status='executing'
                """,
                (json.dumps(result, ensure_ascii=False, default=str), _iso(now), _iso(now), operation_id),
            )
            return _row_to_stored(_fetch(conn, operation_id))

    def fail(self, operation_id: str, error: str, *, now: datetime) -> StoredOperationPlan:
        with _transaction(self._db_path) as conn:
            conn.execute(
                """
                UPDATE operation_plans
                SET status='failed', error=?, finished_at=?, updated_at=?
                WHERE operation_id=? AND status='executing'
                """,
                (error, _iso(now), _iso(now), operation_id),
            )
            return _row_to_stored(_fetch(conn, operation_id))


def _fetch(conn: sqlite3.Connection, operation_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM operation_plans WHERE operation_id=?", (operation_id,)).fetchone()


def _row_to_stored(row: sqlite3.Row | None) -> StoredOperationPlan:
    if row is None:
        raise LookupError("operation plan not found")
    return StoredOperationPlan(
        plan=OperationPlan.model_validate(json.loads(row["plan_json"])),
        status=str(row["status"]),
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        error=row["error"],
    )


def _utc_now() -> str:
    return _iso(datetime.now(timezone.utc))


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class _transaction:
    def __init__(self, db_path: Path | None) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = connect_db(self._db_path, writable=True)
        self._conn.execute("BEGIN IMMEDIATE")
        return self._conn

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        assert self._conn is not None
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
