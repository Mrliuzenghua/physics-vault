import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

from physics_vault_api.repositories.import_tasks import (
    InMemoryImportTaskRepository,
    InvalidTaskTransition,
    SQLiteImportTaskRepository,
)
from physics_vault_api.services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
)


def test_review_tasks_are_persisted_in_sqlite_repository():
    db_path = Path(".codex-run") / f"import-tasks-{uuid4().hex}.sqlite3"
    repo = SQLiteImportTaskRepository(str(db_path))
    service = ImportPipelineService(
        task_repo=repo,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )

    task = service.create_ai_generated_review_task(
        source_text=(
            "1. 已知卫星绕地球做匀速圆周运动，轨道半径为 $r$，"
            "地球质量为 $M$，求线速度。\n"
            "A. $\\sqrt{GM/r}$\n"
            "B. $GM/r$\n"
            "答案：A\n"
            "解析：由万有引力提供向心力。"
        ),
        source="AI 送审测试",
    )

    reloaded_repo = SQLiteImportTaskRepository(str(db_path))
    reloaded_service = ImportPipelineService(
        task_repo=reloaded_repo,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )

    tasks = reloaded_service.list_review_tasks()

    assert tasks[0].task_id == task.task_id
    assert tasks[0].task_type == "ai_generated_review"
    assert tasks[0].result is not None
    assert tasks[0].result["question_count"] == 1


def test_review_task_can_be_deleted_from_sqlite_repository():
    db_path = Path(".codex-run") / f"import-tasks-{uuid4().hex}.sqlite3"
    repo = SQLiteImportTaskRepository(str(db_path))
    service = ImportPipelineService(
        task_repo=repo,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )

    task = service.create_ai_generated_review_task(
        source_text="1. 已知质点做匀加速直线运动，求末速度。\n答案：略\n解析：略",
        source="AI 删除测试",
    )

    assert service.delete_review_task(task.task_id) is True
    assert service.list_review_tasks() == []


def test_review_tasks_migrate_from_legacy_standard_database_once():
    legacy_db_path = Path(".codex-run") / f"legacy-import-tasks-{uuid4().hex}.sqlite3"
    review_db_path = Path(".codex-run") / f"review-import-tasks-{uuid4().hex}.sqlite3"
    legacy_repo = SQLiteImportTaskRepository(str(legacy_db_path))
    legacy_service = ImportPipelineService(
        task_repo=legacy_repo,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    task = legacy_service.create_ai_generated_review_task(
        source_text="1. Legacy review draft\nA. x\n答案：A\n解析：legacy",
        source="legacy-main-db",
    )

    review_repo = SQLiteImportTaskRepository(
        str(review_db_path),
        legacy_db_path=str(legacy_db_path),
        migrate_legacy=True,
    )
    migrated = review_repo.list()
    assert [item.task_id for item in migrated] == [task.task_id]

    new_task = review_repo.create("ai_generated_review", {"source": "review-db"})
    legacy_reloaded = SQLiteImportTaskRepository(str(legacy_db_path))

    assert review_repo.get(new_task.task_id) is not None
    assert legacy_reloaded.get(new_task.task_id) is None


def test_legacy_task_table_is_incrementally_upgraded_without_data_loss(tmp_path: Path):
    db_path = tmp_path / "legacy-tasks.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE import_pipeline_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                input_summary_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO import_pipeline_tasks (
                task_id, task_type, status, created_at, updated_at,
                input_summary_json, result_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-001",
                "convert_document",
                "failed",
                "2026-07-01T00:00:00+00:00",
                "2026-07-01T00:01:00+00:00",
                '{"source_path":"old.docx"}',
                None,
                "legacy failure",
            ),
        )

    repo = SQLiteImportTaskRepository(str(db_path))
    task = repo.get("legacy-001")

    assert task is not None
    assert task.status == "failed"
    assert task.input_summary == {"source_path": "old.docx"}
    assert task.progress == 0
    assert task.attempt == 0
    assert task.max_attempts == 1
    assert task.error_info is not None
    assert task.error_info.error_type == "LegacyTaskError"
    assert task.error_info.message == "legacy failure"

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(import_pipeline_tasks)")}
    assert {
        "progress",
        "current_step",
        "attempt",
        "max_attempts",
        "idempotency_key",
        "message_id",
        "started_at",
        "finished_at",
        "heartbeat_at",
        "result_file_path",
        "error_type",
        "error_message",
        "error_details",
        "error_retryable",
    } <= columns


@pytest.mark.parametrize("repository_kind", ["memory", "sqlite"])
def test_lifecycle_and_structured_error_are_consistent(repository_kind: str, tmp_path: Path):
    repo = (
        InMemoryImportTaskRepository()
        if repository_kind == "memory"
        else SQLiteImportTaskRepository(str(tmp_path / "lifecycle.sqlite3"))
    )
    task = repo.create(
        "ai_clean_markdown",
        {"batch_id": "batch-001"},
        max_attempts=3,
        idempotency_key="clean:batch-001:v1",
        message_id="message-001",
    )
    assert task.status == "pending"
    assert task.progress == 0
    assert task.max_attempts == 3

    running = repo.mark_running(task.task_id, current_step="extract_text", progress=10)
    assert running.status == "running"
    assert running.attempt == 1
    assert running.started_at is not None
    assert running.heartbeat_at is not None

    retrying = repo.mark_retrying(
        task.task_id,
        "gateway timed out",
        error_type="GatewayTimeout",
        user_message="AI 服务暂时无响应，正在重试",
        technical_details="timeout after 30s",
    )
    assert retrying.status == "retrying"
    assert retrying.error_info is not None
    assert retrying.error_info.retryable is True
    assert retrying.error_info.message == "AI 服务暂时无响应，正在重试"

    second_attempt = repo.mark_running(task.task_id, current_step="clean_text", progress=55)
    assert second_attempt.attempt == 2
    completed = repo.mark_completed(
        task.task_id,
        {"batch_id": "batch-001", "count": 4},
        result_file_path="data/results/batch-001.json",
    )
    assert completed.status == "completed"
    assert completed.progress == 100
    assert completed.finished_at is not None
    assert completed.error is None
    assert completed.error_info is None
    assert completed.result_file_path == "data/results/batch-001.json"

    with pytest.raises(InvalidTaskTransition):
        repo.mark_running(task.task_id)


@pytest.mark.parametrize("repository_kind", ["memory", "sqlite"])
def test_task_list_supports_status_type_and_offset_filters(repository_kind: str, tmp_path: Path):
    repo = (
        InMemoryImportTaskRepository()
        if repository_kind == "memory"
        else SQLiteImportTaskRepository(str(tmp_path / "list.sqlite3"))
    )
    completed_id = repo.create("import", {"order": 1}).task_id
    failed_id = repo.create("import", {"order": 2}).task_id
    repo.mark_completed(completed_id, {"ok": True})
    repo.mark_failed(failed_id, "bad input", error_type="InvalidInput")
    repo.create("export", {"order": 3})

    failed = repo.list(limit=10, task_types=["import"], statuses=["failed"])
    assert [task.task_id for task in failed] == [failed_id]
    assert len(repo.list(limit=1, offset=1)) == 1


@pytest.mark.parametrize("repository_kind", ["memory", "sqlite"])
def test_explicit_retry_clears_previous_finished_time(repository_kind: str, tmp_path: Path):
    repo = (
        InMemoryImportTaskRepository()
        if repository_kind == "memory"
        else SQLiteImportTaskRepository(str(tmp_path / "retry.sqlite3"))
    )
    task_id = repo.create("import", {}, max_attempts=2).task_id
    repo.mark_running(task_id)
    failed = repo.mark_failed(task_id, "temporary failure", retryable=True)
    assert failed.finished_at is not None

    retrying = repo.mark_retrying(task_id, "retry requested")
    assert retrying.status == "retrying"
    assert retrying.finished_at is None
    rerun = repo.mark_running(task_id)
    assert rerun.attempt == 2


def test_sqlite_terminal_transition_is_atomic_under_concurrency(tmp_path: Path):
    db_path = tmp_path / "concurrent.sqlite3"
    repo = SQLiteImportTaskRepository(str(db_path))
    task_id = repo.create("import", {}).task_id
    repo.mark_running(task_id)
    barrier = Barrier(2)

    def finish(status: str) -> str:
        local_repo = SQLiteImportTaskRepository(str(db_path))
        barrier.wait()
        try:
            if status == "completed":
                local_repo.mark_completed(task_id, {"winner": status})
            else:
                local_repo.mark_failed(task_id, "worker failed")
            return "updated"
        except InvalidTaskTransition:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(finish, ["completed", "failed"]))

    assert sorted(outcomes) == ["rejected", "updated"]
    persisted = repo.get(task_id)
    assert persisted is not None
    assert persisted.status in {"completed", "failed"}
    with pytest.raises(InvalidTaskTransition):
        repo.mark_running(task_id)


def test_sqlite_repository_enables_wal_and_busy_timeout(tmp_path: Path):
    db_path = tmp_path / "pragmas.sqlite3"
    repo = SQLiteImportTaskRepository(str(db_path))

    conn = repo._connect()
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()

    assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000


@pytest.mark.parametrize("repository_kind", ["memory", "sqlite"])
def test_task_action_audit_is_consistent(repository_kind: str, tmp_path: Path):
    repo = (
        InMemoryImportTaskRepository()
        if repository_kind == "memory"
        else SQLiteImportTaskRepository(str(tmp_path / "action-audit.sqlite3"))
    )
    task = repo.create("background_recognize", {"batch_id": "batch-001"})

    recorded = repo.record_action_audit(
        task.task_id,
        "cancel",
        source="physics_vault_mcp",
        session_id="session-001",
        operator="teacher-001",
        confirmed=True,
        details={"reason": "user requested"},
    )
    loaded = repo.list_action_audits(task.task_id)

    assert loaded == [recorded]
    assert loaded[0].confirmed is True
    assert loaded[0].details == {"reason": "user requested"}
