from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from physics_vault_api.app import create_app
from physics_vault_api.observability import TRACE_ID_HEADER, correlation_context
from physics_vault_api.repositories.import_tasks import SQLiteImportTaskRepository


def test_http_trace_is_returned_and_persisted_on_background_task(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_TASK_QUEUE_ENABLED", "false")
    trace_id = "obs401-http-trace"
    client = TestClient(create_app())

    upload = client.post(
        "/api/import/batches",
        headers={TRACE_ID_HEADER: trace_id},
        files={"file": ("trace.md", b"1. A question", "text/markdown")},
    )
    assert upload.status_code == 200
    assert upload.headers[TRACE_ID_HEADER] == trace_id

    response = client.post(
        f"/api/import/batches/{upload.json()['batch_id']}/recognize-task",
        headers={TRACE_ID_HEADER: trace_id},
    )
    assert response.status_code == 200
    assert response.headers[TRACE_ID_HEADER] == trace_id
    assert response.json()["trace_id"] == trace_id

    task = client.get(f"/api/tasks/{response.json()['task_id']}")
    assert task.status_code == 200
    assert task.json()["trace_id"] == trace_id
    events = client.get(f"/api/tasks/{response.json()['task_id']}/events")
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == ["queued", "started", "completed"]
    assert {event["phase"] for event in events.json()} >= {"queued", "recognize", "complete"}


def test_task_and_audit_share_trace_id(tmp_path: Path) -> None:
    repository = SQLiteImportTaskRepository(str(tmp_path / "review.sqlite3"))

    with correlation_context(trace_id="obs401-durable-trace"):
        task = repository.create("test", {"source": "test"})

    audit = repository.record_action_audit(
        task.task_id,
        "submit",
        source="test",
        session_id=None,
        operator="tester",
        confirmed=True,
    )

    assert task.trace_id == "obs401-durable-trace"
    assert audit.trace_id == task.trace_id
    assert repository.get(task.task_id).trace_id == task.trace_id  # type: ignore[union-attr]
    assert repository.list_action_audits(task.task_id)[0].trace_id == task.trace_id


def test_stage_events_capture_phase_timing_warnings_and_retry_metadata(tmp_path: Path) -> None:
    repository = SQLiteImportTaskRepository(str(tmp_path / "events.sqlite3"))
    task = repository.create("word_export", {"input_version": 7}, trace_id="obs402-stage-trace")
    repository.mark_running(task.task_id, current_step="读取不可变快照")
    repository.update_progress(task.task_id, 15, "准备版式与媒体")
    repository.mark_retrying(task.task_id, "temporary worker error", error_type="WorkerTimeout")
    repository.mark_running(task.task_id, current_step="校验并保存产物")
    repository.mark_completed(task.task_id, {"warnings": ["字体回退"]})

    events = repository.list_stage_events(task.task_id)
    assert [event.event_type for event in events] == [
        "queued", "started", "started", "retrying", "started", "completed", "warning",
    ]
    assert [event.phase for event in events] == [
        "queued", "read", "export", "export", "write", "complete", "complete",
    ]
    assert all(event.trace_id == task.trace_id for event in events)
    assert all(event.input_version == 7 for event in events)
    assert events[1].duration_ms is not None
    assert events[3].error_code == "WorkerTimeout"
    assert events[3].recommended_action == "retry"
    assert events[-1].warning == "字体回退"
