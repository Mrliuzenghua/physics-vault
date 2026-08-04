from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from dramatiq import Worker
from dramatiq.brokers.stub import StubBroker
from fastapi.testclient import TestClient

from physics_vault_api.app import create_app
from physics_vault_api.application import WorkerContainer
from physics_vault_api.config import McpSettings, TaskQueueSettings
from physics_vault_api.repositories.import_tasks import InMemoryImportTaskRepository, SQLiteImportTaskRepository
from physics_vault_api.services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
)
from physics_vault_api.services.task_queue import TaskQueueHealthService
from physics_vault_api.tasks.heartbeat import WorkerHeartbeatMiddleware
from physics_vault_api.tasks.import_pipeline import build_import_actors


class _ActorTestService:
    def __init__(self, *, failures: list[BaseException], max_attempts: int) -> None:
        self.repository = InMemoryImportTaskRepository()
        self.task = self.repository.create(
            "background_recognize",
            {"batch_id": "batch-test", "operation": "recognize"},
            max_attempts=max_attempts,
        )
        self.failures = failures
        self.executions = 0

    def get_task(self, task_id: str):
        task = self.repository.get(task_id)
        assert task is not None
        return task

    def execute_background_batch_task(self, task_id: str, operation: str, batch_id: str):
        claimed = self.repository.claim(task_id, current_step=operation)
        if claimed is None:
            return self.get_task(task_id)
        self.executions += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.repository.mark_completed(task_id, {"batch_id": batch_id})

    def mark_background_task_retrying(self, task_id: str, error: str, **kwargs):
        return self.repository.mark_retrying(task_id, error, **kwargs)

    def fail_background_task(self, task_id: str, error: str, **kwargs):
        return self.repository.mark_failed(task_id, error, **kwargs)


def _run_stub_actor(service: _ActorTestService, settings: TaskQueueSettings) -> None:
    broker = StubBroker(fail_fast_default=False)
    actors = build_import_actors(
        broker,
        settings,
        worker_factory=lambda: SimpleNamespace(import_pipeline_service=service),
    )
    worker = Worker(broker, worker_threads=1, worker_timeout=20)
    worker.start()
    try:
        actors.run_import_batch_stage.send(service.task.task_id, "recognize", "batch-test")
        broker.join(settings.queue_name, timeout=5_000, fail_fast=False)
        broker.join(settings.control_queue_name, timeout=5_000, fail_fast=False)
    finally:
        worker.stop()
        worker.join()


def test_stub_broker_retries_twice_then_succeeds() -> None:
    settings = TaskQueueSettings(
        enabled=True,
        max_retries=2,
        min_backoff_ms=0,
        max_backoff_ms=0,
    )
    service = _ActorTestService(
        failures=[TimeoutError("model timeout"), TimeoutError("model timeout")],
        max_attempts=settings.max_attempts,
    )

    _run_stub_actor(service, settings)

    task = service.get_task(service.task.task_id)
    assert service.executions == 3
    assert task.status == "completed"
    assert task.attempt == 3


def test_stub_broker_does_not_retry_invalid_input() -> None:
    settings = TaskQueueSettings(
        enabled=True,
        max_retries=4,
        min_backoff_ms=0,
        max_backoff_ms=0,
    )
    service = _ActorTestService(
        failures=[ValueError("unsupported file format")],
        max_attempts=settings.max_attempts,
    )

    _run_stub_actor(service, settings)

    task = service.get_task(service.task.task_id)
    assert service.executions == 1
    assert task.status == "failed"
    assert task.error_info is not None
    assert task.error_info.retryable is False


def test_redelivered_message_recovers_abandoned_running_task() -> None:
    settings = TaskQueueSettings(
        enabled=True,
        max_retries=1,
        min_backoff_ms=0,
        max_backoff_ms=0,
        worker_heartbeat_interval_seconds=1,
    )
    service = _ActorTestService(failures=[], max_attempts=settings.max_attempts)
    service.repository.mark_running(service.task.task_id)
    stale = datetime.now(UTC) - timedelta(seconds=10)
    service.repository._tasks[service.task.task_id].heartbeat_at = stale
    service.repository._tasks[service.task.task_id].updated_at = stale

    _run_stub_actor(service, settings)

    task = service.get_task(service.task.task_id)
    assert service.executions == 1
    assert task.status == "completed"
    assert task.attempt == 2


def test_worker_container_recovers_stale_running_task(tmp_path, monkeypatch) -> None:
    review_db = tmp_path / "review.sqlite3"
    monkeypatch.setenv("PHYSICS_REVIEW_DB_PATH", str(review_db))
    repo = SQLiteImportTaskRepository(str(review_db))
    task = repo.create("background_recognize", {}, max_attempts=3)
    repo.mark_running(task.task_id)
    stale = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET heartbeat_at = ?, updated_at = ? WHERE task_id = ?",
            (stale, stale, task.task_id),
        )

    container = WorkerContainer.build(
        mcp_settings=McpSettings(enabled=False),
        task_queue_settings=TaskQueueSettings(enabled=True, stale_task_after_seconds=5),
    )

    recovered = container.import_task_repo.get(task.task_id)
    assert recovered is not None
    assert recovered.status == "retrying"
    assert recovered.error_info is not None
    assert recovered.error_info.error_type == "WorkerHeartbeatExpired"


def test_tasks_health_reports_synchronous_mode(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_TASK_QUEUE_ENABLED", "false")
    client = TestClient(create_app())

    response = client.get("/api/tasks/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["queue_mode"] == "synchronous"
    assert payload["redis_status"] == "disabled"
    assert payload["worker_status"] == "disabled"
    assert payload["backlog"] == 0


def test_health_reports_redis_worker_and_recent_error(monkeypatch) -> None:
    class FakeRedis:
        def ping(self):
            return True

        def scan_iter(self, **_kwargs):
            return [b"physics-vault:worker-heartbeat:test"]

        def get(self, _key):
            return (
                b'{"worker_id":"test","heartbeat_at":"2030-01-02T03:04:05+00:00"}'
            )

    repo = InMemoryImportTaskRepository()
    failed = repo.create("background_recognize", {}, max_attempts=2)
    repo.mark_failed(failed.task_id, "bad input", error_type="ValueError")
    pipeline = ImportPipelineService(
        task_repo=repo,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    health = TaskQueueHealthService(pipeline, TaskQueueSettings(enabled=True))
    monkeypatch.setattr(
        "physics_vault_api.services.task_queue.build_redis_client",
        lambda _settings: FakeRedis(),
    )
    monkeypatch.setattr(health, "_backlog", lambda _client: 7)

    payload = health.check()

    assert payload["redis_status"] == "healthy"
    assert payload["worker_status"] == "healthy"
    assert payload["worker_heartbeat_at"] == "2030-01-02T03:04:05+00:00"
    assert payload["backlog"] == 7
    assert payload["recent_error"]["task_id"] == failed.task_id


def test_worker_heartbeat_middleware_publishes_and_runs_recovery() -> None:
    writes: list[tuple[str, str, int]] = []
    recovered: list[bool] = []

    class FakeClient:
        def set(self, key, value, *, ex):
            writes.append((key, value, ex))

    middleware = WorkerHeartbeatMiddleware(
        TaskQueueSettings(
            worker_heartbeat_interval_seconds=60,
            worker_heartbeat_ttl_seconds=90,
        ),
        recovery=lambda: recovered.append(True),
    )
    middleware.after_process_boot(SimpleNamespace(client=FakeClient()))
    middleware.stop()

    assert recovered == [True]
    assert len(writes) == 1
    assert writes[0][0].startswith("physics-vault:worker-heartbeat:")
    assert writes[0][2] == 90
