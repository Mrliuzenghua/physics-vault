from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import dramatiq
from dramatiq import Actor, Broker

from ..config import TaskQueueSettings
from ..services.task_errors import classify_task_error
from .broker import broker as _broker
from .broker import settings as _settings


@dataclass(frozen=True, slots=True)
class LessonExportActors:
    run_lesson_export: Actor
    mark_lesson_export_failed: Actor


def build_lesson_export_actors(
    broker: Broker,
    settings: TaskQueueSettings,
    worker_factory: Callable[[], Any] | None = None,
) -> LessonExportActors:
    """Build export actors against an injected broker for reliable unit tests."""

    def get_worker() -> Any:
        if worker_factory is not None:
            return worker_factory()
        from ..application import ExportWorkerContainer

        return ExportWorkerContainer.build()

    @dramatiq.actor(
        broker=broker,
        actor_name="mark_lesson_export_failed",
        queue_name=settings.control_queue_name,
        max_retries=0,
    )
    def mark_failed(message_data: dict, retry_data: dict) -> None:
        args = message_data.get("args") or []
        if not args:
            return
        service = get_worker().lesson_export_service
        task_id = str(args[0])
        current = service.get_task(task_id)
        if current.status in {"completed", "cancelled", "failed"}:
            return
        detail = current.error or "Export retry limit exhausted"
        service.mark_failed(
            task_id,
            RuntimeError(f"{detail} (retries={int(retry_data.get('retries') or 0)})"),
            retryable=False,
        )

    def retry_when(retry_count: int, exc: BaseException) -> bool:
        return retry_count < settings.max_retries and classify_task_error(exc).retryable

    @dramatiq.actor(
        broker=broker,
        actor_name="run_lesson_export",
        queue_name=settings.queue_name,
        max_retries=settings.max_retries,
        min_backoff=settings.min_backoff_ms,
        max_backoff=settings.max_backoff_ms,
        time_limit=settings.time_limit_ms,
        retry_when=retry_when,
        on_retry_exhausted="mark_lesson_export_failed",
    )
    def run_export(task_id: str) -> None:
        service = get_worker().lesson_export_service
        current = service.get_task(task_id)
        if current.status in {"completed", "cancelled", "failed"}:
            return
        try:
            service.execute_export_task(task_id)
        except Exception as exc:  # noqa: BLE001
            info = classify_task_error(exc)
            if info.retryable:
                service.mark_retrying(task_id, exc)
            else:
                service.mark_failed(task_id, exc, retryable=False)
            raise

    return LessonExportActors(
        run_lesson_export=run_export,
        mark_lesson_export_failed=mark_failed,
    )


_actors = build_lesson_export_actors(_broker, _settings)
run_lesson_export = _actors.run_lesson_export
mark_lesson_export_failed = _actors.mark_lesson_export_failed


__all__ = [
    "LessonExportActors",
    "build_lesson_export_actors",
    "mark_lesson_export_failed",
    "run_lesson_export",
]
