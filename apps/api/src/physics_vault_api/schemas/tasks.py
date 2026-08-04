from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TaskCenterStatus = Literal[
    "pending",
    "running",
    "retrying",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
]


class TaskErrorInfo(BaseModel):
    error_type: str = "task_error"
    user_message: str
    technical_detail: str | None = None
    retryable: bool = False


class TaskCenterItem(BaseModel):
    task_id: str
    task_type: str
    task_name: str
    status: TaskCenterStatus
    progress: int = Field(default=0, ge=0, le=100)
    current_step: str = ""
    attempt: int = 0
    max_attempts: int = 1
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_available: bool = False
    error: TaskErrorInfo | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] | None = None


class TaskCenterListResponse(BaseModel):
    items: list[TaskCenterItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int


class TaskActionResponse(BaseModel):
    task: TaskCenterItem
    message: str
    original_task_id: str | None = None
