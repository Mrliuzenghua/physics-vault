from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Thread
from typing import Any

import dramatiq
from dramatiq import Actor, Broker

from ..config import TaskQueueSettings
from ..observability import correlation_context
from ..services.task_errors import classify_task_error
from .broker import broker as _broker
from .broker import settings as _settings


@dataclass(frozen=True, slots=True)
class ImportActors:
    run_import_batch_stage: Actor
    mark_import_task_failed: Actor


class _TaskHeartbeat:
    def __init__(self, service: Any, task_id: str, interval_seconds: int) -> None:
        self._repository = getattr(service, "_task_repo", None) or service.repository
        self._task_id = task_id
        self._interval_seconds = max(1, interval_seconds)
        self._stop = Event()
        self._thread = Thread(target=self._run, name=f"task-heartbeat-{task_id[:8]}", daemon=True)

    def __enter__(self) -> "_TaskHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._repository.heartbeat(self._task_id)
            except Exception:  # noqa: BLE001
                # The task may still be pending on the first tick or may have
                # reached a terminal status on the final tick.
                continue


def build_import_actors(
    broker: Broker,
    settings: TaskQueueSettings,
    worker_factory: Callable[[], Any] | None = None,
) -> ImportActors:
    """Build actors against an injected broker for production and StubBroker tests."""

    def get_worker() -> Any:
        if worker_factory is not None:
            return worker_factory()
        from ..application import WorkerContainer

        return WorkerContainer.build(task_queue_settings=settings, recover_stale=False)

    @dramatiq.actor(
        broker=broker,
        actor_name="mark_import_task_failed",
        queue_name=settings.control_queue_name,
        max_retries=0,
    )
    def mark_failed(message_data: dict, retry_data: dict) -> None:
        args = message_data.get("args") or []
        if not args:
            return
        task_id = str(args[0])
        service = get_worker().import_pipeline_service
        current = service.get_task(task_id)
        if current.status in {"completed", "cancelled", "failed"}:
            return
        error_info = current.error_info
        detail = current.error or "后台任务重试次数已耗尽"
        retries = int(retry_data.get("retries") or 0)
        service.fail_background_task(
            task_id,
            detail,
            error_type=error_info.error_type if error_info else "RetryExhaustedError",
            user_message="任务多次重试后仍未成功，请稍后手动重试",
            technical_details=f"{detail} (retries={retries})",
            retryable=False,
        )

    def retry_when(retry_count: int, exc: BaseException) -> bool:
        return retry_count < settings.max_retries and classify_task_error(exc).retryable

    @dramatiq.actor(
        broker=broker,
        actor_name="run_import_batch_stage",
        queue_name=settings.queue_name,
        max_retries=settings.max_retries,
        min_backoff=settings.min_backoff_ms,
        max_backoff=settings.max_backoff_ms,
        time_limit=settings.time_limit_ms,
        retry_when=retry_when,
        on_retry_exhausted="mark_import_task_failed",
    )
    def run_stage(task_id: str, operation: str, batch_id: str) -> None:
        service = get_worker().import_pipeline_service
        current = service.get_task(task_id)
        if current.status == "running":
            repository = getattr(service, "_task_repo", None) or service.repository
            recover_stale = getattr(repository, "recover_stale_tasks", None)
            if callable(recover_stale):
                recover_stale(max(3, settings.worker_heartbeat_interval_seconds * 3))
                current = service.get_task(task_id)
        if current.status in {"completed", "cancelled", "failed"}:
            return
        if current.status == "running":
            # A fresh task heartbeat means another worker still owns this
            # duplicate delivery. The durable task remains the source of truth.
            return
        try:
            with correlation_context(trace_id=current.trace_id, task_id=task_id):
                with _TaskHeartbeat(
                    service,
                    task_id,
                    settings.worker_heartbeat_interval_seconds,
                ):
                    service.execute_background_batch_task(task_id, operation, batch_id)
        except Exception as exc:  # noqa: BLE001
            info = classify_task_error(exc)
            if info.retryable:
                service.mark_background_task_retrying(
                    task_id,
                    info.technical_details,
                    error_type=info.error_type,
                    user_message=info.user_message,
                    technical_details=info.technical_details,
                )
            else:
                service.fail_background_task(
                    task_id,
                    info.technical_details,
                    error_type=info.error_type,
                    user_message=info.user_message,
                    technical_details=info.technical_details,
                    retryable=False,
                )
            raise

    return ImportActors(
        run_import_batch_stage=run_stage,
        mark_import_task_failed=mark_failed,
    )


_actors = build_import_actors(_broker, _settings)
run_import_batch_stage = _actors.run_import_batch_stage
mark_import_task_failed = _actors.mark_import_task_failed


__all__ = [
    "ImportActors",
    "build_import_actors",
    "mark_import_task_failed",
    "run_import_batch_stage",
]
