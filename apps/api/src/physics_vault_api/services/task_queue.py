from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from redis import Redis

from ..config import TaskQueueSettings
from ..observability import correlation_context, current_context
from ..repositories.import_tasks import ImportTask
from ..schemas.lesson_exports import LessonExportRequest
from .document_pipeline import ImportPipelineService
from .lesson_exports import ExportFormat, LessonExportService


class ImportTaskDispatcher:
    """Submit durable import work while preserving a synchronous dev mode."""

    def __init__(
        self,
        service: ImportPipelineService,
        settings: TaskQueueSettings | None = None,
    ) -> None:
        self._service = service
        self.settings = settings or TaskQueueSettings.from_env()

    def submit_batch_stage(
        self,
        operation: str,
        batch_id: str,
        *,
        request_context: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> ImportTask:
        correlated_context = current_context().as_request_context()
        correlated_context.update(request_context or {})
        task, should_dispatch = self._service.prepare_background_batch_task(
            operation,
            batch_id,
            max_attempts=self.settings.max_attempts,
            request_context=correlated_context,
            idempotency_key=idempotency_key,
        )
        if not should_dispatch:
            return task
        if not self.settings.enabled:
            try:
                with correlation_context(trace_id=task.trace_id, task_id=task.task_id):
                    return self._service.execute_background_batch_task(task.task_id, operation, batch_id)
            except Exception as exc:  # noqa: BLE001
                return self._service.fail_background_task(task.task_id, str(exc))

        try:
            from ..tasks.import_pipeline import run_import_batch_stage

            message = run_import_batch_stage.send(task.task_id, operation, batch_id)
            set_message_id = getattr(self._service._task_repo, "set_message_id", None)
            if callable(set_message_id):
                task = set_message_id(task.task_id, message.message_id)
        except Exception as exc:  # noqa: BLE001
            self._service.fail_background_task(
                task.task_id,
                f"任务入队失败：{exc}",
                error_type=exc.__class__.__name__,
                user_message="后台任务队列暂时不可用，请稍后重试",
                technical_details=str(exc),
                retryable=True,
            )
            raise HTTPException(status_code=503, detail="后台任务队列暂不可用，请检查 Redis 和 worker") from exc
        return task

    def status(self) -> dict[str, str | bool]:
        return {
            "enabled": self.settings.enabled,
            "mode": "dramatiq" if self.settings.enabled else "synchronous",
            "broker": "redis" if self.settings.enabled else "none",
            "namespace": self.settings.namespace,
        }


class LessonExportDispatcher:
    """Queue Office exports while retaining the no-Redis synchronous mode."""

    def __init__(
        self,
        service: LessonExportService,
        settings: TaskQueueSettings | None = None,
    ) -> None:
        self._service = service
        self.settings = settings or TaskQueueSettings.from_env()

    def submit(
        self,
        export_format: ExportFormat,
        payload: LessonExportRequest,
        *,
        request_context: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> ImportTask:
        correlated_context = current_context().as_request_context()
        correlated_context.update(request_context or {})
        task = self._service.create_export_task(
            export_format,
            payload,
            max_attempts=self.settings.max_attempts,
            request_context=correlated_context,
            idempotency_key=idempotency_key,
        )
        return self._dispatch(task)

    def retry(self, task_id: str) -> ImportTask:
        task = self._service.clone_for_retry(task_id, max_attempts=self.settings.max_attempts)
        return self._dispatch(task)

    def _dispatch(self, task: ImportTask) -> ImportTask:
        if task.status in {"completed", "running", "retrying", "cancel_requested"}:
            return task
        if task.status == "pending" and task.message_id:
            return task
        if not self.settings.enabled:
            try:
                with correlation_context(trace_id=task.trace_id, task_id=task.task_id):
                    return self._service.execute_export_task(task.task_id)
            except Exception as exc:  # noqa: BLE001
                return self._service.mark_failed(task.task_id, exc)

        try:
            from ..tasks.lesson_exports import run_lesson_export

            message = run_lesson_export.send(task.task_id)
            return self._service.set_message_id(task.task_id, message.message_id)
        except Exception as exc:  # noqa: BLE001
            self._service.mark_failed(task.task_id, exc, retryable=True)
            raise HTTPException(
                status_code=503,
                detail="后台导出队列暂不可用，组卷页将回退到浏览器导出。",
            ) from exc
        return self._service.get_task(task.task_id)


class TaskQueueHealthService:
    """Inspect Redis transport, worker liveness and durable task failures."""

    def __init__(
        self,
        service: ImportPipelineService,
        settings: TaskQueueSettings | None = None,
    ) -> None:
        self._service = service
        self.settings = settings or TaskQueueSettings.from_env()

    def check(self) -> dict[str, Any]:
        recent_error = self._recent_error()
        base: dict[str, Any] = {
            "queue_mode": "dramatiq" if self.settings.enabled else "synchronous",
            "namespace": self.settings.namespace,
            "redis_status": "disabled",
            "redis_reachable": False,
            "worker_status": "disabled",
            "worker_heartbeat_at": None,
            "backlog": 0,
            "recent_error": recent_error,
        }
        if not self.settings.enabled:
            return base

        try:
            client = build_redis_client(self.settings)
            client.ping()
            base["redis_status"] = "healthy"
            base["redis_reachable"] = True
            base["backlog"] = self._backlog(client)
            heartbeat = self._latest_worker_heartbeat(client)
            if heartbeat is None:
                base["worker_status"] = "missing"
            else:
                base["worker_status"] = "healthy"
                base["worker_heartbeat_at"] = heartbeat
        except Exception as exc:  # noqa: BLE001
            base["redis_status"] = "unavailable"
            base["worker_status"] = "unknown"
            base["backlog"] = None
            base["redis_error"] = str(exc)
        return base

    def _backlog(self, client: Redis) -> int:
        from dramatiq.brokers.redis import RedisBroker

        broker = RedisBroker(client=client, namespace=self.settings.namespace)
        return sum(
            int(broker.do_qsize(queue_name))
            for queue_name in (self.settings.queue_name, self.settings.control_queue_name)
        )

    def _latest_worker_heartbeat(self, client: Redis) -> str | None:
        latest: datetime | None = None
        pattern = f"{self.settings.namespace}:worker-heartbeat:*"
        for key in client.scan_iter(match=pattern, count=100):
            raw = client.get(key)
            if not raw:
                continue
            try:
                payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
                timestamp = datetime.fromisoformat(str(payload["heartbeat_at"]).replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            if latest is None or timestamp > latest:
                latest = timestamp
        return latest.astimezone(UTC).isoformat() if latest else None

    def _recent_error(self) -> dict[str, Any] | None:
        repository = self._service._task_repo
        tasks = repository.list(limit=1, statuses=["failed", "retrying"])
        if not tasks:
            return None
        task = tasks[0]
        info = task.error_info
        return {
            "task_id": task.task_id,
            "error_type": info.error_type if info else "TaskExecutionError",
            "message": info.message if info else task.error,
            "at": task.updated_at.isoformat(),
        }


def build_redis_client(settings: TaskQueueSettings) -> Redis:
    return Redis.from_url(
        settings.broker_url,
        socket_connect_timeout=settings.redis_timeout_seconds,
        socket_timeout=settings.redis_timeout_seconds,
        decode_responses=False,
    )


__all__ = ["ImportTaskDispatcher", "TaskQueueHealthService", "build_redis_client"]
