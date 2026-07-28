from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4


TaskStatus = Literal["pending", "running", "completed", "failed"]


@dataclass(slots=True)
class ImportTask:
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    input_summary: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None


class InMemoryImportTaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, ImportTask] = {}

    def create(self, task_type: str, input_summary: dict[str, Any]) -> ImportTask:
        now = datetime.now(UTC)
        task = ImportTask(
            task_id=str(uuid4()),
            task_type=task_type,
            status="pending",
            created_at=now,
            updated_at=now,
            input_summary=input_summary,
        )
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> ImportTask | None:
        return self._tasks.get(task_id)

    def mark_running(self, task_id: str) -> ImportTask:
        task = self._tasks[task_id]
        task.status = "running"
        task.updated_at = datetime.now(UTC)
        return task

    def mark_completed(self, task_id: str, result: dict[str, Any]) -> ImportTask:
        task = self._tasks[task_id]
        task.status = "completed"
        task.result = result
        task.error = None
        task.updated_at = datetime.now(UTC)
        return task

    def mark_failed(self, task_id: str, error: str) -> ImportTask:
        task = self._tasks[task_id]
        task.status = "failed"
        task.error = error
        task.updated_at = datetime.now(UTC)
        return task

