from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from physics_vault_api.config import TaskQueueSettings
from physics_vault_api.paths import project_root
from physics_vault_api.repositories.import_tasks import InMemoryImportTaskRepository
from physics_vault_api.routers.tasks import build_tasks_router
from physics_vault_api.services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
)
from physics_vault_api.services.lesson_exports import LessonExportService
from physics_vault_api.services.task_center import TaskCenterService
from physics_vault_api.services.task_queue import LessonExportDispatcher


class StubDispatcher:
    def __init__(self, repository: InMemoryImportTaskRepository) -> None:
        self.repository = repository
        self.submissions: list[tuple[str, str]] = []
        self.settings = TaskQueueSettings(enabled=False)

    def submit_batch_stage(self, operation: str, batch_id: str, *, request_context=None, idempotency_key=None):
        self.submissions.append((operation, batch_id))
        summary = {
            "operation": operation,
            "batch_id": batch_id,
            "request_context": request_context or {},
        }
        if idempotency_key:
            task, _ = self.repository.create_or_get(
                f"background_{operation}", summary, idempotency_key=idempotency_key
            )
            return task
        return self.repository.create(f"background_{operation}", summary)


def build_client():
    repository = InMemoryImportTaskRepository()
    import_service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    dispatcher = StubDispatcher(repository)
    task_service = TaskCenterService(import_service, dispatcher=dispatcher)  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(build_tasks_router(task_service))
    return TestClient(app), repository, dispatcher


def test_task_list_supports_status_type_filter_and_pagination() -> None:
    client, repository, _ = build_client()
    first = repository.create("background_recognize", {"batch_id": "batch-1", "operation": "recognize"})
    repository.mark_failed(first.task_id, "network timeout", retryable=True)
    second = repository.create("background_recognize", {"batch_id": "batch-2", "operation": "recognize"})
    repository.mark_failed(second.task_id, "bad file")
    repository.create("background_ai_clean", {"batch_id": "batch-3", "operation": "ai_clean"})

    response = client.get(
        "/api/tasks",
        params={"status": "failed", "task_type": "background_recognize", "page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["pages"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["status"] == "failed"
    assert payload["items"][0]["error"]["technical_detail"]


def test_task_detail_cancel_and_retry_are_persisted() -> None:
    client, repository, dispatcher = build_client()
    pending = repository.create("background_ai_clean", {"batch_id": "batch-cancel", "operation": "ai_clean"})

    cancelled = client.post(f"/api/tasks/{pending.task_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["task"]["status"] == "cancel_requested"
    assert client.get(f"/api/tasks/{pending.task_id}").json()["status"] == "cancel_requested"

    failed = repository.create("background_recognize", {"batch_id": "batch-retry", "operation": "recognize"})
    repository.mark_failed(failed.task_id, "temporary error", retryable=True)
    retried = client.post(f"/api/tasks/{failed.task_id}/retry")

    assert retried.status_code == 200
    assert retried.json()["original_task_id"] == failed.task_id
    assert retried.json()["task"]["task_id"] != failed.task_id
    assert dispatcher.submissions == [("recognize", "batch-retry")]


def test_download_returns_declared_result_and_rejects_outside_path(tmp_path: Path) -> None:
    client, repository, _ = build_client()
    result_path = project_root() / ".codex-run" / f"task-result-{uuid4().hex}.txt"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text("downloadable", encoding="utf-8")
    try:
        task = repository.create("background_recognize", {"batch_id": "download", "operation": "recognize"})
        repository.mark_completed(task.task_id, {"status": "completed"}, result_file_path=str(result_path))
        response = client.get(f"/api/tasks/{task.task_id}/download")
        assert response.status_code == 200
        assert response.content == b"downloadable"
    finally:
        result_path.unlink(missing_ok=True)

    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    unsafe = repository.create("background_recognize", {"batch_id": "unsafe", "operation": "recognize"})
    repository.mark_completed(unsafe.task_id, {"status": "completed"}, result_file_path=str(outside))

    rejected = client.get(f"/api/tasks/{unsafe.task_id}/download")
    assert rejected.status_code == 404


def test_mcp_submission_records_source_session_operator_and_audit() -> None:
    _client, repository, dispatcher = build_client()
    import_service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    service = TaskCenterService(import_service, dispatcher=dispatcher)  # type: ignore[arg-type]
    from physics_vault_api.services.task_center import TaskActionContext

    task, audit_id = service.submit_batch_job(
        "ai_clean",
        "batch-audit",
        context=TaskActionContext(
            source="physics_vault_mcp",
            session_id="session-42",
            operator="teacher-li",
        ),
    )

    persisted = repository.get(task["task_id"])
    assert persisted is not None
    request_context = persisted.input_summary["request_context"]
    assert {key: request_context[key] for key in ("source", "session_id", "operator")} == {
        "source": "physics_vault_mcp",
        "session_id": "session-42",
        "operator": "teacher-li",
    }
    assert request_context["trace_id"] == persisted.trace_id
    audits = repository.list_action_audits(task["task_id"])
    assert [item.audit_id for item in audits] == [audit_id]
    assert audits[0].action == "submit_ai_clean"
    assert audits[0].session_id == "session-42"
    assert audits[0].operator == "teacher-li"


def test_operation_id_makes_task_submission_idempotent() -> None:
    _client, repository, dispatcher = build_client()
    import_service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    service = TaskCenterService(import_service, dispatcher=dispatcher)  # type: ignore[arg-type]
    from physics_vault_api.services.task_center import TaskActionContext

    context = TaskActionContext(operation_id="import-batch-001")
    first, _ = service.submit_batch_job("recognize", "batch-idempotent", context=context)
    replay, _ = service.submit_batch_job("recognize", "batch-idempotent", context=context)

    assert replay["task_id"] == first["task_id"]
    assert len(repository.list(limit=20)) == 1


def test_active_task_limit_rejects_new_submission_but_allows_replay() -> None:
    _client, repository, dispatcher = build_client()
    dispatcher.settings.max_active_tasks = 1
    import_service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    service = TaskCenterService(import_service, dispatcher=dispatcher)  # type: ignore[arg-type]
    from physics_vault_api.services.task_center import TaskActionContext

    first, _ = service.submit_batch_job(
        "recognize", "batch-one", context=TaskActionContext(operation_id="capacity-one")
    )
    replay, _ = service.submit_batch_job(
        "recognize", "batch-one", context=TaskActionContext(operation_id="capacity-one")
    )
    assert replay["task_id"] == first["task_id"]

    with pytest.raises(HTTPException) as exc_info:
        service.submit_batch_job(
            "recognize", "batch-two", context=TaskActionContext(operation_id="capacity-two")
        )
    assert exc_info.value.status_code == 429


def test_mcp_word_export_uses_formal_export_service_and_returns_download(tmp_path: Path) -> None:
    repository = InMemoryImportTaskRepository()
    import_service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    export_service = LessonExportService(
        repository,
        export_dir=tmp_path / "exports",
        project_dir=tmp_path,
    )
    export_dispatcher = LessonExportDispatcher(
        export_service,
        settings=TaskQueueSettings(enabled=False),
    )
    service = TaskCenterService(
        import_service,
        lesson_export_service=export_service,
        export_dispatcher=export_dispatcher,
    )
    from physics_vault_api.services.task_center import TaskActionContext

    task, audit_id = service.submit_export_job(
        "word",
        {
            "id": "lesson-001",
            "revision": 3,
            "title": "牛顿第二定律",
            "questions": [],
            "nodes": [],
        },
        include_answers=True,
        include_analysis=False,
        file_name="课堂练习",
        context=TaskActionContext(session_id="session-export", operator="teacher-li"),
    )

    assert task["status"] == "completed"
    assert task["task_type"] == "word_export"
    assert task["result_summary"]["export_format"] == "word"
    path, filename = service.resolve_result_file(task["task_id"])
    assert path.is_file()
    assert filename.endswith(".docx")
    assert repository.list_action_audits(task["task_id"])[0].audit_id == audit_id
    persisted = repository.get(task["task_id"])
    assert persisted is not None
    assert persisted.input_summary["request_context"]["session_id"] == "session-export"

    duplicate, duplicate_audit_id = service.submit_export_job(
        "word",
        {
            "id": "lesson-001",
            "revision": 3,
            "title": "牛顿第二定律",
            "questions": [],
            "nodes": [],
        },
        include_answers=True,
        include_analysis=False,
        file_name="课堂练习",
        context=TaskActionContext(session_id="session-export-2", operator="teacher-li"),
    )
    assert duplicate["task_id"] == task["task_id"]
    assert duplicate_audit_id != audit_id
    assert len(repository.list_action_audits(task["task_id"])) == 2


def test_export_submission_enforces_question_limit(tmp_path: Path) -> None:
    repository = InMemoryImportTaskRepository()
    import_service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    export_service = LessonExportService(repository, export_dir=tmp_path / "exports", project_dir=tmp_path)
    service = TaskCenterService(
        import_service,
        lesson_export_service=export_service,
        export_dispatcher=LessonExportDispatcher(export_service, settings=TaskQueueSettings(enabled=False)),
    )
    service._dispatcher.settings.max_export_questions = 1
    from physics_vault_api.services.task_center import TaskActionContext

    with pytest.raises(HTTPException) as exc_info:
        service.submit_export_job(
            "word",
            {"id": "lesson-limit", "title": "limit", "questions": [{}, {}], "nodes": []},
            include_answers=False,
            include_analysis=False,
            file_name=None,
            context=TaskActionContext(operation_id="export-limit"),
        )
    assert exc_info.value.status_code == 413
