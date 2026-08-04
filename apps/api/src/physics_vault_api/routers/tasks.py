from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from ..schemas.tasks import TaskActionResponse, TaskCenterItem, TaskCenterListResponse
from ..services.task_center import TaskCenterService
from ..services.task_queue import TaskQueueHealthService


VALID_STATUSES = {
    "pending",
    "running",
    "retrying",
    "cancel_requested",
    "cancelled",
    "completed",
    "failed",
}


def build_tasks_router(service: TaskCenterService) -> APIRouter:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])
    queue_health = TaskQueueHealthService(
        service._import_service,
        settings=service._dispatcher.settings,
    )

    @router.get("", response_model=TaskCenterListResponse)
    def list_tasks(
        status: Annotated[list[str] | None, Query()] = None,
        task_type: Annotated[list[str] | None, Query()] = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> TaskCenterListResponse:
        statuses = [item for raw in (status or []) for item in raw.split(",") if item in VALID_STATUSES]
        task_types = [item for raw in (task_type or []) for item in raw.split(",") if item]
        items, total = service.list_tasks(
            statuses=statuses or None,
            task_types=task_types or None,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        return TaskCenterListResponse(
            items=[TaskCenterItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )

    @router.get("/health")
    def get_task_queue_health() -> dict:
        return queue_health.check()

    @router.get("/{task_id}", response_model=TaskCenterItem)
    def get_task(task_id: str) -> TaskCenterItem:
        return TaskCenterItem.model_validate(service.get_task(task_id))

    @router.post("/{task_id}/retry", response_model=TaskActionResponse)
    def retry_task(task_id: str) -> TaskActionResponse:
        task, original_task_id = service.retry_task(task_id)
        return TaskActionResponse(
            task=TaskCenterItem.model_validate(task),
            message="已创建重试任务",
            original_task_id=original_task_id,
        )

    @router.post("/{task_id}/cancel", response_model=TaskActionResponse)
    def cancel_task(task_id: str) -> TaskActionResponse:
        task = service.cancel_task(task_id)
        status = str(task["status"])
        message = "任务已取消" if status == "cancelled" else "已提交取消请求"
        return TaskActionResponse(task=TaskCenterItem.model_validate(task), message=message)

    @router.get("/{task_id}/download", response_class=FileResponse)
    def download_task_result(task_id: str) -> FileResponse:
        path, filename = service.resolve_result_file(task_id)
        return FileResponse(path, filename=filename)

    return router
