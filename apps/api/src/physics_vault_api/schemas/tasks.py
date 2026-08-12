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
    trace_id: str = ""
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


class TaskStageEventItem(BaseModel):
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
    details: dict[str, Any] = Field(default_factory=dict)


class TaskCenterListResponse(BaseModel):
    items: list[TaskCenterItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int


class TaskQueueRecentError(BaseModel):
    task_id: str
    error_type: str
    message: str | None = None
    at: str


class TaskQueueHealthResponse(BaseModel):
    queue_mode: str
    namespace: str
    redis_status: str
    redis_reachable: bool
    worker_status: str
    worker_heartbeat_at: str | None = None
    backlog: int | None = 0
    recent_error: TaskQueueRecentError | None = None
    redis_error: str | None = None


class TaskActionResponse(BaseModel):
    task: TaskCenterItem
    message: str
    original_task_id: str | None = None


class TaskArtifactItem(BaseModel):
    display_name: str
    download_url: str
    type: str


class TaskAuditItem(BaseModel):
    audit_id: str
    action: str
    created_at: datetime
    operator: str
    confirmed: bool


class TaskContextResponse(BaseModel):
    artifacts: list[TaskArtifactItem] = Field(default_factory=list)
    audits: list[TaskAuditItem] = Field(default_factory=list)
    retry_allowed: bool
    retry_reason: str
