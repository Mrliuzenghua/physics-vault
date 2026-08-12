from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal, cast
from uuid import uuid4

from ..database import connect_db
from ..db_schema import ensure_import_task_lifecycle_schema
from ..observability import resolve_trace_id
from ..paths import default_review_db_path


TaskStatus = Literal[
    "pending",
    "running",
    "retrying",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
]

TASK_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "running",
        "retrying",
        "cancel_requested",
        "cancelled",
        "completed",
        "failed",
    }
)
TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"cancelled", "completed", "failed"})

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"pending", "running", "cancel_requested", "cancelled", "completed", "failed"}),
    "running": frozenset({"running", "retrying", "cancel_requested", "cancelled", "completed", "failed"}),
    "retrying": frozenset({"retrying", "running", "cancel_requested", "cancelled", "failed"}),
    "cancel_requested": frozenset({"cancel_requested", "cancelled", "completed", "failed"}),
    "cancelled": frozenset({"cancelled"}),
    "completed": frozenset({"completed"}),
    # A future explicit retry operation may move a failed task to retrying, but
    # ordinary worker execution cannot move it directly back to running.
    "failed": frozenset({"failed", "retrying"}),
}

_UNSET = object()


class InvalidTaskTransition(RuntimeError):
    def __init__(self, task_id: str, current_status: str, requested_status: str) -> None:
        super().__init__(f"Task {task_id} cannot transition from {current_status} to {requested_status}")
        self.task_id = task_id
        self.current_status = current_status
        self.requested_status = requested_status


@dataclass(frozen=True, slots=True)
class TaskErrorInfo:
    error_type: str
    message: str
    technical_details: str | None = None
    retryable: bool = False


@dataclass(slots=True)
class ImportTask:
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    input_summary: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    # Kept for API and database compatibility. New consumers should prefer
    # error_info, which separates a user-facing message from technical detail.
    error: str | None = None
    progress: int = 0
    current_step: str | None = None
    attempt: int = 0
    max_attempts: int = 1
    idempotency_key: str | None = None
    message_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    result_file_path: str | None = None
    error_info: TaskErrorInfo | None = None
    trace_id: str = ""


@dataclass(frozen=True, slots=True)
class TaskActionAudit:
    audit_id: str
    task_id: str
    action: str
    source: str
    session_id: str | None
    operator: str
    confirmed: bool
    details: dict[str, Any]
    created_at: datetime
    trace_id: str = ""


@dataclass(slots=True)
class TaskStageEvent:
    event_id: str
    task_id: str
    trace_id: str
    phase: str
    stage: str
    event_type: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    input_version: int | None = None
    retry_count: int = 0
    warning: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    recommended_action: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class InMemoryImportTaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, ImportTask] = {}
        self._action_audits: list[TaskActionAudit] = []
        self._stage_events: list[TaskStageEvent] = []
        self._lock = RLock()

    def create(
        self,
        task_type: str,
        input_summary: dict[str, Any],
        *,
        max_attempts: int = 1,
        idempotency_key: str | None = None,
        message_id: str | None = None,
        trace_id: str | None = None,
    ) -> ImportTask:
        now = datetime.now(UTC)
        task = ImportTask(
            task_id=str(uuid4()),
            task_type=task_type,
            status="pending",
            created_at=now,
            updated_at=now,
            input_summary=deepcopy(input_summary),
            max_attempts=max(1, int(max_attempts)),
            idempotency_key=idempotency_key,
            message_id=message_id,
            trace_id=_resolve_task_trace_id(trace_id, input_summary),
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._append_stage_event(task, phase="queued", stage="queued", event_type="queued", now=now, finish=True)
            return deepcopy(task)

    def create_or_get(
        self,
        task_type: str,
        input_summary: dict[str, Any],
        *,
        max_attempts: int = 1,
        idempotency_key: str,
        message_id: str | None = None,
        trace_id: str | None = None,
    ) -> tuple[ImportTask, bool]:
        """Create once for an idempotency key, atomically within the repository."""
        with self._lock:
            matches = [task for task in self._tasks.values() if task.idempotency_key == idempotency_key]
            if matches:
                latest = max(matches, key=lambda item: (item.created_at, item.task_id))
                return deepcopy(latest), False
            return (
                self.create(
                    task_type,
                    input_summary,
                    max_attempts=max_attempts,
                    idempotency_key=idempotency_key,
                    message_id=message_id,
                    trace_id=trace_id,
                ),
                True,
            )

    def find_by_idempotency_key(self, idempotency_key: str) -> ImportTask | None:
        with self._lock:
            matches = [task for task in self._tasks.values() if task.idempotency_key == idempotency_key]
            if not matches:
                return None
            return deepcopy(max(matches, key=lambda item: (item.created_at, item.task_id)))

    def claim(self, task_id: str, *, current_step: str | None = None) -> ImportTask | None:
        """Claim pending/retrying work once; duplicate consumers receive ``None``."""
        with self._lock:
            task = self._require_task(task_id)
            if task.status not in {"pending", "retrying"}:
                return None
            return self.mark_running(task_id, current_step=current_step)

    def get(self, task_id: str) -> ImportTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return deepcopy(task) if task else None

    def mark_running(
        self,
        task_id: str,
        *,
        current_step: str | None = None,
        progress: int | None = None,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "running",
            current_step=current_step,
            progress=progress,
            clear_error=True,
            touch_heartbeat=True,
        )

    def mark_retrying(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "retrying",
            error=error,
            error_info=TaskErrorInfo(
                error_type=error_type,
                message=user_message or error,
                technical_details=technical_details or error,
                retryable=True,
            ),
            touch_heartbeat=True,
        )

    def mark_completed(
        self,
        task_id: str,
        result: dict[str, Any],
        *,
        result_file_path: str | None = None,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "completed",
            result=deepcopy(result),
            result_file_path=result_file_path,
            progress=100,
            clear_error=True,
        )

    def mark_failed(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
        retryable: bool = False,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "failed",
            error=error,
            error_info=TaskErrorInfo(
                error_type=error_type,
                message=user_message or error,
                technical_details=technical_details or error,
                retryable=retryable,
            ),
        )

    def request_cancel(self, task_id: str) -> ImportTask:
        return self._transition(task_id, "cancel_requested", current_step="cancel_requested")

    def mark_cancelled(self, task_id: str, message: str | None = None) -> ImportTask:
        return self._transition(task_id, "cancelled", current_step=message or "cancelled")

    def update_progress(self, task_id: str, progress: int, current_step: str | None = None) -> ImportTask:
        with self._lock:
            task = self._require_task(task_id)
            if task.status in TERMINAL_TASK_STATUSES:
                raise InvalidTaskTransition(task_id, task.status, task.status)
            task.progress = _normalize_progress(progress)
            previous_step = task.current_step
            if current_step is not None:
                task.current_step = current_step
            now = datetime.now(UTC)
            task.updated_at = now
            task.heartbeat_at = now
            if current_step and current_step != previous_step:
                self._close_open_stage_events(task_id, now)
                self._append_stage_event(task, phase=_phase_for(current_step, task.task_type), stage=current_step, event_type="started", now=now)
            return deepcopy(task)

    def heartbeat(self, task_id: str) -> ImportTask:
        with self._lock:
            task = self._require_task(task_id)
            if task.status not in {"running", "retrying", "cancel_requested"}:
                raise InvalidTaskTransition(task_id, task.status, task.status)
            now = datetime.now(UTC)
            task.updated_at = now
            task.heartbeat_at = now
            return deepcopy(task)

    def set_message_id(self, task_id: str, message_id: str) -> ImportTask:
        with self._lock:
            task = self._require_task(task_id)
            task.message_id = message_id
            task.updated_at = datetime.now(UTC)
            return deepcopy(task)

    def recover_stale_tasks(self, stale_after_seconds: int) -> list[ImportTask]:
        """Move abandoned active tasks to retrying or fail exhausted work."""
        cutoff = datetime.now(UTC) - timedelta(seconds=max(1, int(stale_after_seconds)))
        recovered: list[ImportTask] = []
        with self._lock:
            for task in self._tasks.values():
                last_seen = task.heartbeat_at or task.updated_at
                if task.status not in {"running", "retrying"} or last_seen >= cutoff:
                    continue
                message = "Worker 心跳超时，等待队列重新投递"
                if task.attempt >= task.max_attempts:
                    recovered.append(
                        self.mark_failed(
                            task.task_id,
                            message,
                            error_type="WorkerHeartbeatExpired",
                            technical_details=f"last heartbeat: {last_seen.isoformat()}",
                        )
                    )
                else:
                    recovered.append(
                        self.mark_retrying(
                            task.task_id,
                            message,
                            error_type="WorkerHeartbeatExpired",
                            technical_details=f"last heartbeat: {last_seen.isoformat()}",
                        )
                    )
        return recovered

    def list(
        self,
        limit: int = 50,
        task_types: list[str] | None = None,
        *,
        statuses: list[TaskStatus] | None = None,
        offset: int = 0,
    ) -> list[ImportTask]:
        with self._lock:
            tasks = list(self._tasks.values())
            if task_types:
                allowed_types = set(task_types)
                tasks = [task for task in tasks if task.task_type in allowed_types]
            if statuses:
                invalid = set(statuses) - TASK_STATUSES
                if invalid:
                    raise ValueError(f"Unknown task statuses: {sorted(invalid)}")
                allowed_statuses = set(statuses)
                tasks = [task for task in tasks if task.status in allowed_statuses]
            tasks.sort(key=lambda task: (task.updated_at, task.created_at), reverse=True)
            start = max(0, int(offset or 0))
            end = start + _normalize_limit(limit)
            return deepcopy(tasks[start:end])

    def delete(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def record_action_audit(
        self,
        task_id: str,
        action: str,
        *,
        source: str,
        session_id: str | None,
        operator: str,
        confirmed: bool,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> TaskActionAudit:
        with self._lock:
            self._require_task(task_id)
            audit = TaskActionAudit(
                audit_id=str(uuid4()),
                task_id=task_id,
                action=action,
                source=source,
                session_id=session_id,
                operator=operator,
                confirmed=bool(confirmed),
                details=deepcopy(details or {}),
                created_at=datetime.now(UTC),
                trace_id=resolve_trace_id(trace_id or self._require_task(task_id).trace_id),
            )
            self._action_audits.append(audit)
            return deepcopy(audit)

    def list_action_audits(self, task_id: str, limit: int = 50) -> list[TaskActionAudit]:
        with self._lock:
            audits = [item for item in self._action_audits if item.task_id == task_id]
            audits.sort(key=lambda item: item.created_at, reverse=True)
            return deepcopy(audits[:_normalize_limit(limit)])

    def list_stage_events(self, task_id: str, limit: int = 200) -> list[TaskStageEvent]:
        with self._lock:
            events = [item for item in self._stage_events if item.task_id == task_id]
            # Events emitted by one transition intentionally share a timestamp.
            # Python's stable sort preserves their append order in that case,
            # which keeps a terminal event before its attached warnings.
            events.sort(key=lambda item: item.started_at)
            return deepcopy(events[:_normalize_limit(limit)])

    def _require_task(self, task_id: str) -> ImportTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _transition(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        progress: int | None = None,
        current_step: str | None = None,
        result: dict[str, Any] | object = _UNSET,
        result_file_path: str | None | object = _UNSET,
        error: str | None | object = _UNSET,
        error_info: TaskErrorInfo | None | object = _UNSET,
        clear_error: bool = False,
        touch_heartbeat: bool = False,
    ) -> ImportTask:
        with self._lock:
            task = self._require_task(task_id)
            _validate_transition(task_id, task.status, status)
            previous_status = task.status
            now = datetime.now(UTC)
            task.status = status
            task.updated_at = now
            if status == "running":
                if previous_status in {"pending", "retrying"}:
                    task.attempt += 1
                task.started_at = task.started_at or now
            if status in TERMINAL_TASK_STATUSES:
                task.finished_at = task.finished_at or now
            else:
                task.finished_at = None
            if progress is not None:
                task.progress = _normalize_progress(progress)
            if current_step is not None:
                task.current_step = current_step
            if result is not _UNSET:
                task.result = cast(dict[str, Any], result)
            if result_file_path is not _UNSET:
                task.result_file_path = cast(str | None, result_file_path)
            if clear_error:
                task.error = None
                task.error_info = None
            else:
                if error is not _UNSET:
                    task.error = cast(str | None, error)
                if error_info is not _UNSET:
                    task.error_info = cast(TaskErrorInfo | None, error_info)
            if touch_heartbeat:
                task.heartbeat_at = now
            self._record_transition_events(task, previous_status, status, now, error_info, result)
            return deepcopy(task)

    def _record_transition_events(
        self,
        task: ImportTask,
        previous_status: TaskStatus,
        status: TaskStatus,
        now: datetime,
        error_info: TaskErrorInfo | None | object,
        result: dict[str, Any] | object,
    ) -> None:
        if status == "running":
            self._close_open_stage_events(task.task_id, now)
            self._append_stage_event(task, phase=_phase_for(task.current_step, task.task_type), stage=task.current_step or "processing", event_type="started", now=now)
        elif status == "retrying":
            self._close_open_stage_events(task.task_id, now)
            info = error_info if isinstance(error_info, TaskErrorInfo) else task.error_info
            self._append_stage_event(task, phase=_phase_for(task.current_step, task.task_type), stage=task.current_step or "processing", event_type="retrying", now=now, finish=True, error_info=info)
        elif status in TERMINAL_TASK_STATUSES:
            self._close_open_stage_events(task.task_id, now)
            event_type = "completed" if status == "completed" else status
            info = error_info if isinstance(error_info, TaskErrorInfo) else task.error_info
            self._append_stage_event(task, phase="complete", stage=task.current_step or status, event_type=event_type, now=now, finish=True, error_info=info)
            if isinstance(result, dict):
                for warning in result.get("warnings") or []:
                    self._append_stage_event(task, phase="complete", stage=task.current_step or status, event_type="warning", now=now, finish=True, warning=str(warning))
        elif status == "cancel_requested" and previous_status != status:
            self._close_open_stage_events(task.task_id, now)
            self._append_stage_event(task, phase="complete", stage="cancel_requested", event_type="started", now=now)

    def _append_stage_event(
        self,
        task: ImportTask,
        *,
        phase: str,
        stage: str,
        event_type: str,
        now: datetime,
        finish: bool = False,
        error_info: TaskErrorInfo | None = None,
        warning: str | None = None,
    ) -> None:
        self._stage_events.append(
            _new_stage_event(task, phase=phase, stage=stage, event_type=event_type, now=now, finish=finish, error_info=error_info, warning=warning)
        )

    def _close_open_stage_events(self, task_id: str, now: datetime) -> None:
        for event in self._stage_events:
            if event.task_id == task_id and event.finished_at is None:
                event.finished_at = now
                event.duration_ms = _duration_ms(event.started_at, now)


class SQLiteImportTaskRepository:
    """Durable task repository with incremental migrations and atomic transitions."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        legacy_db_path: str | None = None,
        migrate_legacy: bool = False,
    ) -> None:
        self._db_path = db_path or str(default_review_db_path())
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        if legacy_db_path and migrate_legacy:
            self._migrate_legacy_tasks(legacy_db_path)

    def _connect(self) -> sqlite3.Connection:
        return connect_db(self._db_path, writable=True)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_import_task_lifecycle_schema(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate_legacy_tasks(self, legacy_db_path: str) -> None:
        legacy_path = Path(legacy_db_path)
        target_path = Path(self._db_path)
        if not legacy_path.exists() or legacy_path.resolve() == target_path.resolve():
            return

        source = connect_db(legacy_path, writable=False)
        try:
            table = source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'import_pipeline_tasks'"
            ).fetchone()
            if table is None:
                return
            rows = source.execute(
                """
                SELECT task_id, task_type, status, created_at, updated_at,
                       input_summary_json, result_json, error
                FROM import_pipeline_tasks
                """
            ).fetchall()
        finally:
            source.close()

        if not rows:
            return

        target = self._connect()
        try:
            target.execute("BEGIN IMMEDIATE")
            target.executemany(
                """
                INSERT OR IGNORE INTO import_pipeline_tasks (
                    task_id, task_type, status, created_at, updated_at,
                    input_summary_json, result_json, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [tuple(row) for row in rows],
            )
            target.commit()
        except Exception:
            target.rollback()
            raise
        finally:
            target.close()

    def create(
        self,
        task_type: str,
        input_summary: dict[str, Any],
        *,
        max_attempts: int = 1,
        idempotency_key: str | None = None,
        message_id: str | None = None,
        trace_id: str | None = None,
    ) -> ImportTask:
        now = datetime.now(UTC)
        task = ImportTask(
            task_id=str(uuid4()),
            task_type=task_type,
            status="pending",
            created_at=now,
            updated_at=now,
            input_summary=deepcopy(input_summary),
            max_attempts=max(1, int(max_attempts)),
            idempotency_key=idempotency_key,
            message_id=message_id,
            trace_id=_resolve_task_trace_id(trace_id, input_summary),
        )
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO import_pipeline_tasks (
                    task_id, task_type, status, created_at, updated_at,
                    input_summary_json, result_json, error, progress,
                    current_step, attempt, max_attempts, idempotency_key,
                    message_id, started_at, finished_at, heartbeat_at,
                    result_file_path, error_type, error_message,
                    error_details, error_retryable, trace_id
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 0,
                        NULL, 0, ?, ?, ?, NULL, NULL, NULL,
                        NULL, NULL, NULL, NULL, 0, ?)
                """,
                (
                    task.task_id,
                    task.task_type,
                    task.status,
                    _dt_to_text(task.created_at),
                    _dt_to_text(task.updated_at),
                    json.dumps(task.input_summary, ensure_ascii=False),
                    task.max_attempts,
                    task.idempotency_key,
                    task.message_id,
                    task.trace_id,
                ),
            )
            _insert_stage_event(
                conn,
                _new_stage_event(task, phase="queued", stage="queued", event_type="queued", now=now, finish=True),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return task

    def create_or_get(
        self,
        task_type: str,
        input_summary: dict[str, Any],
        *,
        max_attempts: int = 1,
        idempotency_key: str,
        message_id: str | None = None,
        trace_id: str | None = None,
    ) -> tuple[ImportTask, bool]:
        """Serialize lookup+insert so concurrent submitters share one task."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM import_pipeline_tasks
                WHERE idempotency_key = ?
                ORDER BY created_at DESC, task_id DESC
                LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                conn.commit()
                return _row_to_task(row), False

            now = datetime.now(UTC)
            task = ImportTask(
                task_id=str(uuid4()),
                task_type=task_type,
                status="pending",
                created_at=now,
                updated_at=now,
                input_summary=deepcopy(input_summary),
                max_attempts=max(1, int(max_attempts)),
                idempotency_key=idempotency_key,
                message_id=message_id,
                trace_id=_resolve_task_trace_id(trace_id, input_summary),
            )
            conn.execute(
                """
                INSERT INTO import_pipeline_tasks (
                    task_id, task_type, status, created_at, updated_at,
                    input_summary_json, result_json, error, progress,
                    current_step, attempt, max_attempts, idempotency_key,
                    message_id, started_at, finished_at, heartbeat_at,
                    result_file_path, error_type, error_message,
                    error_details, error_retryable, trace_id
                )
                VALUES (?, ?, 'pending', ?, ?, ?, NULL, NULL, 0,
                        NULL, 0, ?, ?, ?, NULL, NULL, NULL,
                        NULL, NULL, NULL, NULL, 0, ?)
                """,
                (
                    task.task_id,
                    task.task_type,
                    _dt_to_text(now),
                    _dt_to_text(now),
                    json.dumps(task.input_summary, ensure_ascii=False),
                    task.max_attempts,
                    task.idempotency_key,
                    task.message_id,
                    task.trace_id,
                ),
            )
            _insert_stage_event(
                conn,
                _new_stage_event(task, phase="queued", stage="queued", event_type="queued", now=now, finish=True),
            )
            conn.commit()
            return task, True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def find_by_idempotency_key(self, idempotency_key: str) -> ImportTask | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM import_pipeline_tasks
                WHERE idempotency_key = ?
                ORDER BY created_at DESC, task_id DESC
                LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
        finally:
            conn.close()
        return _row_to_task(row) if row else None

    def claim(self, task_id: str, *, current_step: str | None = None) -> ImportTask | None:
        """Atomically move pending/retrying work to running exactly once."""
        now = datetime.now(UTC)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            previous_row = conn.execute(
                "SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            cursor = conn.execute(
                """
                UPDATE import_pipeline_tasks
                SET status = 'running', updated_at = ?,
                    started_at = COALESCE(started_at, ?),
                    heartbeat_at = ?, current_step = COALESCE(?, current_step),
                    attempt = attempt + 1,
                    error = NULL, error_type = NULL, error_message = NULL,
                    error_details = NULL, error_retryable = 0
                WHERE task_id = ? AND status IN ('pending', 'retrying')
                """,
                (
                    _dt_to_text(now),
                    _dt_to_text(now),
                    _dt_to_text(now),
                    current_step,
                    task_id,
                ),
            )
            if cursor.rowcount != 1:
                exists = conn.execute(
                    "SELECT 1 FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if exists is None:
                    raise KeyError(task_id)
                conn.commit()
                return None
            row = conn.execute("SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if previous_row is not None and row is not None:
                _record_sqlite_transition_events(
                    conn,
                    _row_to_task(cast(sqlite3.Row, previous_row)),
                    _row_to_task(cast(sqlite3.Row, row)),
                    status="running",
                    now=now,
                    error_info=_UNSET,
                    result=_UNSET,
                )
            conn.commit()
            return _row_to_task(cast(sqlite3.Row, row))
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, task_id: str) -> ImportTask | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
        finally:
            conn.close()
        return _row_to_task(row) if row else None

    def mark_running(
        self,
        task_id: str,
        *,
        current_step: str | None = None,
        progress: int | None = None,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "running",
            current_step=current_step,
            progress=progress,
            clear_error=True,
            touch_heartbeat=True,
        )

    def mark_retrying(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "retrying",
            error=error,
            error_info=TaskErrorInfo(
                error_type=error_type,
                message=user_message or error,
                technical_details=technical_details or error,
                retryable=True,
            ),
            touch_heartbeat=True,
        )

    def mark_completed(
        self,
        task_id: str,
        result: dict[str, Any],
        *,
        result_file_path: str | None = None,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "completed",
            result=deepcopy(result),
            result_file_path=result_file_path,
            progress=100,
            clear_error=True,
        )

    def mark_failed(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
        retryable: bool = False,
    ) -> ImportTask:
        return self._transition(
            task_id,
            "failed",
            error=error,
            error_info=TaskErrorInfo(
                error_type=error_type,
                message=user_message or error,
                technical_details=technical_details or error,
                retryable=retryable,
            ),
        )

    def request_cancel(self, task_id: str) -> ImportTask:
        return self._transition(task_id, "cancel_requested", current_step="cancel_requested")

    def mark_cancelled(self, task_id: str, message: str | None = None) -> ImportTask:
        return self._transition(task_id, "cancelled", current_step=message or "cancelled")

    def update_progress(self, task_id: str, progress: int, current_step: str | None = None) -> ImportTask:
        normalized = _normalize_progress(progress)
        now = datetime.now(UTC)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            previous_row = conn.execute(
                "SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            cursor = conn.execute(
                """
                UPDATE import_pipeline_tasks
                SET progress = ?, current_step = COALESCE(?, current_step),
                    updated_at = ?, heartbeat_at = ?
                WHERE task_id = ?
                  AND status IN ('pending', 'running', 'retrying', 'cancel_requested')
                """,
                (normalized, current_step, _dt_to_text(now), _dt_to_text(now), task_id),
            )
            if cursor.rowcount == 0:
                self._raise_missing_or_invalid(conn, task_id, "progress_update")
            row = conn.execute("SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if current_step and previous_row is not None:
                previous_task = _row_to_task(cast(sqlite3.Row, previous_row))
                updated_task = _row_to_task(cast(sqlite3.Row, row))
                if previous_task.current_step != updated_task.current_step:
                    _close_open_stage_events(conn, task_id, now)
                    _insert_stage_event(
                        conn,
                        _new_stage_event(
                            updated_task,
                            phase=_phase_for(updated_task.current_step, updated_task.task_type),
                            stage=updated_task.current_step or "processing",
                            event_type="started",
                            now=now,
                        ),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return _row_to_task(cast(sqlite3.Row, row))

    def heartbeat(self, task_id: str) -> ImportTask:
        now = datetime.now(UTC)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE import_pipeline_tasks
                SET updated_at = ?, heartbeat_at = ?
                WHERE task_id = ? AND status IN ('running', 'retrying', 'cancel_requested')
                """,
                (_dt_to_text(now), _dt_to_text(now), task_id),
            )
            if cursor.rowcount == 0:
                self._raise_missing_or_invalid(conn, task_id, "heartbeat")
            row = conn.execute("SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return _row_to_task(cast(sqlite3.Row, row))

    def set_message_id(self, task_id: str, message_id: str) -> ImportTask:
        now = datetime.now(UTC)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE import_pipeline_tasks SET message_id = ?, updated_at = ? WHERE task_id = ?",
                (message_id, _dt_to_text(now), task_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(task_id)
            row = conn.execute("SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return _row_to_task(cast(sqlite3.Row, row))

    def recover_stale_tasks(self, stale_after_seconds: int) -> list[ImportTask]:
        """Atomically recover tasks left active by a terminated worker."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=max(1, int(stale_after_seconds)))
        recovered_ids: list[str] = []
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            stale_rows = conn.execute(
                """
                SELECT task_id, attempt, max_attempts,
                       COALESCE(heartbeat_at, updated_at) AS last_seen
                FROM import_pipeline_tasks
                WHERE status IN ('running', 'retrying')
                  AND COALESCE(heartbeat_at, updated_at) < ?
                """,
                (_dt_to_text(cutoff),),
            ).fetchall()
            for row in stale_rows:
                task_id = str(row["task_id"])
                exhausted = int(row["attempt"] or 0) >= max(1, int(row["max_attempts"] or 1))
                status = "failed" if exhausted else "retrying"
                message = "Worker 心跳超时，等待队列重新投递"
                conn.execute(
                    """
                    UPDATE import_pipeline_tasks
                    SET status = ?, updated_at = ?, finished_at = ?,
                        error = ?, error_type = 'WorkerHeartbeatExpired',
                        error_message = ?, error_details = ?, error_retryable = ?
                    WHERE task_id = ? AND status IN ('running', 'retrying')
                    """,
                    (
                        status,
                        _dt_to_text(now),
                        _dt_to_text(now) if exhausted else None,
                        message,
                        message,
                        f"last heartbeat: {row['last_seen']}",
                        0 if exhausted else 1,
                        task_id,
                    ),
                )
                recovered_ids.append(task_id)
            recovered = [
                conn.execute(
                    "SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                for task_id in recovered_ids
            ]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return [_row_to_task(row) for row in recovered if row is not None]

    def list(
        self,
        limit: int = 50,
        task_types: list[str] | None = None,
        *,
        statuses: list[TaskStatus] | None = None,
        offset: int = 0,
    ) -> list[ImportTask]:
        params: list[Any] = []
        clauses: list[str] = []
        if task_types:
            placeholders = ",".join("?" for _ in task_types)
            clauses.append(f"task_type IN ({placeholders})")
            params.extend(task_types)
        if statuses:
            invalid = set(statuses) - TASK_STATUSES
            if invalid:
                raise ValueError(f"Unknown task statuses: {sorted(invalid)}")
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([_normalize_limit(limit), max(0, int(offset or 0))])
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM import_pipeline_tasks
                {where}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_task(row) for row in rows]

    def delete(self, task_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute("DELETE FROM import_pipeline_tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_action_audit(
        self,
        task_id: str,
        action: str,
        *,
        source: str,
        session_id: str | None,
        operator: str,
        confirmed: bool,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> TaskActionAudit:
        now = datetime.now(UTC)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            exists = conn.execute(
                "SELECT 1 FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(task_id)
            audit = TaskActionAudit(
                audit_id=str(uuid4()),
                task_id=task_id,
                action=action,
                source=source,
                session_id=session_id,
                operator=operator,
                confirmed=bool(confirmed),
                details=deepcopy(details or {}),
                created_at=now,
                trace_id=resolve_trace_id(trace_id or _task_trace_id(conn, task_id)),
            )
            conn.execute(
                """
                INSERT INTO task_action_audit (
                    audit_id, task_id, action, source, session_id, operator,
                    confirmed, details_json, created_at, trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit.audit_id,
                    audit.task_id,
                    audit.action,
                    audit.source,
                    audit.session_id,
                    audit.operator,
                    int(audit.confirmed),
                    json.dumps(audit.details, ensure_ascii=False),
                    _dt_to_text(audit.created_at),
                    audit.trace_id,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return audit

    def list_action_audits(self, task_id: str, limit: int = 50) -> list[TaskActionAudit]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM task_action_audit
                WHERE task_id = ?
                ORDER BY created_at DESC, audit_id DESC
                LIMIT ?
                """,
                (task_id, _normalize_limit(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [
            TaskActionAudit(
                audit_id=str(row["audit_id"]),
                task_id=str(row["task_id"]),
                action=str(row["action"]),
                source=str(row["source"]),
                session_id=str(row["session_id"]) if row["session_id"] else None,
                operator=str(row["operator"]),
                confirmed=bool(row["confirmed"]),
                details=_json_dict(row["details_json"]),
                created_at=cast(datetime, _dt_from_text(str(row["created_at"]))),
                trace_id=str(row["trace_id"]) if row["trace_id"] else "",
            )
            for row in rows
        ]

    def list_stage_events(self, task_id: str, limit: int = 200) -> list[TaskStageEvent]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM task_stage_events
                WHERE task_id = ?
                -- Several events can be emitted in one transition and share a
                -- timestamp. rowid preserves their insertion order, matching
                -- the in-memory repository and the user-facing timeline.
                ORDER BY started_at ASC, rowid ASC
                LIMIT ?
                """,
                (task_id, _normalize_limit(limit)),
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_stage_event(row) for row in rows]

    def _transition(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        progress: int | None = None,
        current_step: str | None = None,
        result: dict[str, Any] | object = _UNSET,
        result_file_path: str | None | object = _UNSET,
        error: str | None | object = _UNSET,
        error_info: TaskErrorInfo | None | object = _UNSET,
        clear_error: bool = False,
        touch_heartbeat: bool = False,
    ) -> ImportTask:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if current is None:
                raise KeyError(task_id)
            previous_task = _row_to_task(cast(sqlite3.Row, current))
            previous_status = previous_task.status
            _validate_transition(task_id, previous_status, status)

            now = datetime.now(UTC)
            assignments = ["status = ?", "updated_at = ?"]
            params: list[Any] = [status, _dt_to_text(now)]
            if status == "running":
                assignments.extend(
                    [
                        "started_at = COALESCE(started_at, ?)",
                        "attempt = CASE WHEN status IN ('pending', 'retrying') THEN attempt + 1 ELSE attempt END",
                    ]
                )
                params.append(_dt_to_text(now))
            if status in TERMINAL_TASK_STATUSES:
                assignments.append("finished_at = COALESCE(finished_at, ?)")
                params.append(_dt_to_text(now))
            else:
                assignments.append("finished_at = NULL")
            if progress is not None:
                assignments.append("progress = ?")
                params.append(_normalize_progress(progress))
            if current_step is not None:
                assignments.append("current_step = ?")
                params.append(current_step)
            if result is not _UNSET:
                assignments.append("result_json = ?")
                params.append(json.dumps(result, ensure_ascii=False))
            if result_file_path is not _UNSET:
                assignments.append("result_file_path = ?")
                params.append(result_file_path)
            if clear_error:
                assignments.extend(
                    [
                        "error = NULL",
                        "error_type = NULL",
                        "error_message = NULL",
                        "error_details = NULL",
                        "error_retryable = 0",
                    ]
                )
            else:
                if error is not _UNSET:
                    assignments.append("error = ?")
                    params.append(error)
                if error_info is not _UNSET:
                    info = cast(TaskErrorInfo | None, error_info)
                    assignments.extend(
                        [
                            "error_type = ?",
                            "error_message = ?",
                            "error_details = ?",
                            "error_retryable = ?",
                        ]
                    )
                    params.extend(
                        [
                            info.error_type if info else None,
                            info.message if info else None,
                            info.technical_details if info else None,
                            int(info.retryable) if info else 0,
                        ]
                    )
            if touch_heartbeat:
                assignments.append("heartbeat_at = ?")
                params.append(_dt_to_text(now))

            params.extend([task_id, previous_status])
            cursor = conn.execute(
                f"UPDATE import_pipeline_tasks SET {', '.join(assignments)} WHERE task_id = ? AND status = ?",
                params,
            )
            if cursor.rowcount != 1:
                self._raise_missing_or_invalid(conn, task_id, status)
            row = conn.execute("SELECT * FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
            updated_task = _row_to_task(cast(sqlite3.Row, row))
            _record_sqlite_transition_events(
                conn,
                previous_task,
                updated_task,
                status=status,
                now=now,
                error_info=error_info,
                result=result,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return _row_to_task(cast(sqlite3.Row, row))

    @staticmethod
    def _raise_missing_or_invalid(conn: sqlite3.Connection, task_id: str, requested: str) -> None:
        row = conn.execute("SELECT status FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        raise InvalidTaskTransition(task_id, str(row["status"]), requested)


def _validate_transition(task_id: str, current_status: str, requested_status: str) -> None:
    if requested_status not in TASK_STATUSES:
        raise ValueError(f"Unknown task status: {requested_status}")
    allowed = _ALLOWED_TRANSITIONS.get(current_status, frozenset())
    if requested_status not in allowed:
        raise InvalidTaskTransition(task_id, current_status, requested_status)


def _normalize_progress(progress: int) -> int:
    value = int(progress)
    if value < 0 or value > 100:
        raise ValueError("Task progress must be between 0 and 100")
    return value


def _normalize_limit(limit: int) -> int:
    return max(1, min(int(limit or 50), 200))


def _dt_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _dt_from_text(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _resolve_task_trace_id(trace_id: str | None, input_summary: dict[str, Any]) -> str:
    request_context = input_summary.get("request_context")
    contextual_trace = request_context.get("trace_id") if isinstance(request_context, dict) else None
    return resolve_trace_id(trace_id or str(contextual_trace or ""))


def _task_trace_id(conn: sqlite3.Connection, task_id: str) -> str | None:
    row = conn.execute(
        "SELECT trace_id FROM import_pipeline_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    return str(row["trace_id"]) if row and row["trace_id"] else None


def _phase_for(current_step: str | None, task_type: str) -> str:
    value = str(current_step or "").lower()
    task_kind = str(task_type or "").lower()
    if not value:
        return "export" if task_kind.endswith("_export") else "queued"
    if any(token in value for token in ("read", "读取")):
        return "read"
    if any(token in value for token in ("pandoc", "convert", "转换", "转化")):
        return "convert"
    if any(token in value for token in ("clean", "清洗")):
        return "clean"
    if any(token in value for token in ("recognize", "识别")):
        return "recognize"
    if any(token in value for token in ("parse", "structure", "解析", "结构")):
        return "parse"
    if any(token in value for token in ("save", "write", "校验", "保存", "写入")):
        return "write"
    if task_kind.endswith("_export"):
        return "export"
    return "transform"


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _input_version(task: ImportTask) -> int | None:
    value = task.input_summary.get("input_version")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _recommended_action(error_info: TaskErrorInfo | None) -> str | None:
    if error_info is None:
        return None
    return "retry" if error_info.retryable else "check_input_or_configuration"


def _new_stage_event(
    task: ImportTask,
    *,
    phase: str,
    stage: str,
    event_type: str,
    now: datetime,
    finish: bool = False,
    error_info: TaskErrorInfo | None = None,
    warning: str | None = None,
) -> TaskStageEvent:
    return TaskStageEvent(
        event_id=str(uuid4()),
        task_id=task.task_id,
        trace_id=task.trace_id or resolve_trace_id(),
        phase=phase,
        stage=str(stage or phase),
        event_type=event_type,
        started_at=now,
        finished_at=now if finish else None,
        duration_ms=0 if finish else None,
        input_version=_input_version(task),
        retry_count=task.attempt,
        warning=warning,
        error_code=error_info.error_type if error_info else None,
        error_message=error_info.message if error_info else None,
        recommended_action=_recommended_action(error_info),
    )


def _insert_stage_event(conn: sqlite3.Connection, event: TaskStageEvent) -> None:
    conn.execute(
        """
        INSERT INTO task_stage_events (
            event_id, task_id, trace_id, phase, stage, event_type,
            started_at, finished_at, duration_ms, input_version, retry_count,
            warning, error_code, error_message, recommended_action, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.task_id,
            event.trace_id,
            event.phase,
            event.stage,
            event.event_type,
            _dt_to_text(event.started_at),
            _dt_to_text(event.finished_at) if event.finished_at else None,
            event.duration_ms,
            event.input_version,
            event.retry_count,
            event.warning,
            event.error_code,
            event.error_message,
            event.recommended_action,
            json.dumps(event.details, ensure_ascii=False),
            _dt_to_text(event.started_at),
        ),
    )


def _close_open_stage_events(conn: sqlite3.Connection, task_id: str, now: datetime) -> None:
    rows = conn.execute(
        "SELECT event_id, started_at FROM task_stage_events WHERE task_id = ? AND finished_at IS NULL",
        (task_id,),
    ).fetchall()
    for row in rows:
        started_at = _dt_from_text(str(row["started_at"])) or now
        conn.execute(
            "UPDATE task_stage_events SET finished_at = ?, duration_ms = ? WHERE event_id = ?",
            (_dt_to_text(now), _duration_ms(started_at, now), row["event_id"]),
        )


def _record_sqlite_transition_events(
    conn: sqlite3.Connection,
    previous_task: ImportTask,
    task: ImportTask,
    *,
    status: TaskStatus,
    now: datetime,
    error_info: TaskErrorInfo | None | object,
    result: dict[str, Any] | object,
) -> None:
    if status == "running":
        _close_open_stage_events(conn, task.task_id, now)
        _insert_stage_event(conn, _new_stage_event(task, phase=_phase_for(task.current_step, task.task_type), stage=task.current_step or "processing", event_type="started", now=now))
    elif status == "retrying":
        _close_open_stage_events(conn, task.task_id, now)
        info = error_info if isinstance(error_info, TaskErrorInfo) else task.error_info
        _insert_stage_event(conn, _new_stage_event(task, phase=_phase_for(task.current_step, task.task_type), stage=task.current_step or "processing", event_type="retrying", now=now, finish=True, error_info=info))
    elif status in TERMINAL_TASK_STATUSES:
        _close_open_stage_events(conn, task.task_id, now)
        event_type = "completed" if status == "completed" else status
        info = error_info if isinstance(error_info, TaskErrorInfo) else task.error_info
        _insert_stage_event(conn, _new_stage_event(task, phase="complete", stage=task.current_step or status, event_type=event_type, now=now, finish=True, error_info=info))
        if isinstance(result, dict):
            for warning in result.get("warnings") or []:
                _insert_stage_event(conn, _new_stage_event(task, phase="complete", stage=task.current_step or status, event_type="warning", now=now, finish=True, warning=str(warning)))
    elif status == "cancel_requested" and previous_task.status != status:
        _close_open_stage_events(conn, task.task_id, now)
        _insert_stage_event(conn, _new_stage_event(task, phase="complete", stage="cancel_requested", event_type="started", now=now))


def _row_to_stage_event(row: sqlite3.Row) -> TaskStageEvent:
    return TaskStageEvent(
        event_id=str(row["event_id"]),
        task_id=str(row["task_id"]),
        trace_id=str(row["trace_id"]),
        phase=str(row["phase"]),
        stage=str(row["stage"]),
        event_type=str(row["event_type"]),
        started_at=cast(datetime, _dt_from_text(str(row["started_at"]))),
        finished_at=_dt_from_text(row["finished_at"]),
        duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        input_version=int(row["input_version"]) if row["input_version"] is not None else None,
        retry_count=int(row["retry_count"] or 0),
        warning=str(row["warning"]) if row["warning"] else None,
        error_code=str(row["error_code"]) if row["error_code"] else None,
        error_message=str(row["error_message"]) if row["error_message"] else None,
        recommended_action=str(row["recommended_action"]) if row["recommended_action"] else None,
        details=_json_dict(row["details_json"]),
    )


def _row_to_task(row: sqlite3.Row) -> ImportTask:
    legacy_error = str(row["error"]) if row["error"] else None
    error_message = str(row["error_message"]) if row["error_message"] else None
    error_info: TaskErrorInfo | None = None
    if legacy_error or error_message:
        error_info = TaskErrorInfo(
            error_type=str(row["error_type"] or "LegacyTaskError"),
            message=error_message or legacy_error or "Task failed",
            technical_details=str(row["error_details"] or legacy_error) if row["error_details"] or legacy_error else None,
            retryable=bool(row["error_retryable"]),
        )
    status = str(row["status"])
    return ImportTask(
        task_id=str(row["task_id"]),
        task_type=str(row["task_type"]),
        status=cast(TaskStatus, status),
        created_at=cast(datetime, _dt_from_text(str(row["created_at"]))),
        updated_at=cast(datetime, _dt_from_text(str(row["updated_at"]))),
        input_summary=_json_dict(row["input_summary_json"]),
        result=_json_dict(row["result_json"]) if row["result_json"] else None,
        error=legacy_error,
        progress=int(row["progress"] or 0),
        current_step=str(row["current_step"]) if row["current_step"] else None,
        attempt=int(row["attempt"] or 0),
        max_attempts=max(1, int(row["max_attempts"] or 1)),
        idempotency_key=str(row["idempotency_key"]) if row["idempotency_key"] else None,
        message_id=str(row["message_id"]) if row["message_id"] else None,
        started_at=_dt_from_text(row["started_at"]),
        finished_at=_dt_from_text(row["finished_at"]),
        heartbeat_at=_dt_from_text(row["heartbeat_at"]),
        result_file_path=str(row["result_file_path"]) if row["result_file_path"] else None,
        error_info=error_info,
        trace_id=str(row["trace_id"]) if row["trace_id"] else "",
    )
