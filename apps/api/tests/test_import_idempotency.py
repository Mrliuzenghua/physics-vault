from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

import pytest

from physics_vault_api.repositories.import_tasks import (
    InMemoryImportTaskRepository,
    SQLiteImportTaskRepository,
)
from physics_vault_api.services import document_pipeline as pipeline_module
from physics_vault_api.services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    StaleBatchVersionError,
    StructuredQuestionParsingService,
)


class CountingPandoc:
    def __init__(self, *, block: bool = False) -> None:
        self.calls = 0
        self._lock = Lock()
        self.entered = Event()
        self.release = Event()
        if not block:
            self.release.set()

    def unpack_to_markdown(self, source_path: str, markdown_path: str, media_dir: str) -> dict:
        with self._lock:
            self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=5)
        target = Path(markdown_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("1. Stable question\nA. One\nB. Two", encoding="utf-8")
        Path(media_dir).mkdir(parents=True, exist_ok=True)
        return {"images": [], "text": target.read_text(encoding="utf-8")}


@pytest.fixture
def pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    batches = tmp_path / "batches"
    monkeypatch.setattr(pipeline_module, "default_import_batches_dir", lambda: batches)
    monkeypatch.setattr(pipeline_module, "project_root", lambda: tmp_path)
    adapter = CountingPandoc()
    repository = InMemoryImportTaskRepository()
    service = ImportPipelineService(
        task_repo=repository,
        pandoc=adapter,  # type: ignore[arg-type]
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    return service, repository, adapter


def test_identical_submissions_reuse_active_and_completed_task(pipeline) -> None:
    service, _repository, adapter = pipeline
    batch_id = service.create_batch_from_upload("same.md", b"question")["batch_id"]

    first, first_should_dispatch = service.prepare_background_batch_task("pandoc", batch_id)
    second, second_should_dispatch = service.prepare_background_batch_task("pandoc", batch_id)

    assert first.task_id == second.task_id
    assert first.idempotency_key == second.idempotency_key
    assert first_should_dispatch is True
    assert second_should_dispatch is False

    completed = service.execute_background_batch_task(first.task_id, "pandoc", batch_id)
    cached, cached_should_dispatch = service.prepare_background_batch_task("pandoc", batch_id)

    assert completed.status == "completed"
    assert cached.task_id == first.task_id
    assert cached_should_dispatch is False
    assert service.execute_background_batch_task(first.task_id, "pandoc", batch_id).status == "completed"
    assert adapter.calls == 1


def test_sqlite_concurrent_submission_creates_one_idempotent_task(tmp_path: Path) -> None:
    repository = SQLiteImportTaskRepository(str(tmp_path / "tasks.sqlite3"))

    def submit():
        return repository.create_or_get(
            "background_ai_clean",
            {"batch_id": "batch-1"},
            idempotency_key="stable-key",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [future.result(timeout=5) for future in (pool.submit(submit), pool.submit(submit))]

    assert first[0].task_id == second[0].task_id
    assert sorted([first[1], second[1]]) == [False, True]
    assert len(repository.list(task_types=["background_ai_clean"])) == 1


def test_duplicate_consumers_claim_one_batch_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    batches = tmp_path / "batches"
    monkeypatch.setattr(pipeline_module, "default_import_batches_dir", lambda: batches)
    monkeypatch.setattr(pipeline_module, "project_root", lambda: tmp_path)
    adapter = CountingPandoc(block=True)
    repository = InMemoryImportTaskRepository()
    service = ImportPipelineService(
        task_repo=repository,
        pandoc=adapter,  # type: ignore[arg-type]
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    batch_id = service.create_batch_from_upload("race.md", b"question")["batch_id"]
    task, _ = service.prepare_background_batch_task("pandoc", batch_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.execute_background_batch_task, task.task_id, "pandoc", batch_id)
        assert adapter.entered.wait(timeout=5)
        second = pool.submit(service.execute_background_batch_task, task.task_id, "pandoc", batch_id)
        second.result(timeout=5)
        adapter.release.set()
        assert first.result(timeout=5).status == "completed"

    assert adapter.calls == 1
    assert service.get_task(task.task_id).status == "completed"


def test_completed_stage_checkpoint_resumes_without_reprocessing(pipeline) -> None:
    service, _repository, adapter = pipeline
    batch_id = service.create_batch_from_upload("resume.md", b"question")["batch_id"]

    first = service.run_batch_pandoc(batch_id)
    resumed = service.run_batch_pandoc(batch_id)

    assert resumed.task_id == first.task_id
    assert adapter.calls == 1
    status = service.get_batch_status(batch_id)
    assert status["completed_stages"]["pandoc"]["task_id"] == first.task_id


def test_task_can_resume_after_worker_dies_before_stage_side_effects(pipeline) -> None:
    service, repository, adapter = pipeline
    batch_id = service.create_batch_from_upload("crash.md", b"question")["batch_id"]
    task, _ = service.prepare_background_batch_task("pandoc", batch_id)

    assert repository.claim(task.task_id, current_step="pandoc") is not None
    repository.mark_retrying(task.task_id, "worker process exited")
    resumed = service.execute_background_batch_task(task.task_id, "pandoc", batch_id)

    assert resumed.status == "completed"
    assert resumed.attempt == 2
    assert adapter.calls == 1


def test_late_worker_cannot_overwrite_confirmed_user_edit(pipeline) -> None:
    service, _repository, adapter = pipeline
    batch_id = service.create_batch_from_upload("late.md", b"question")["batch_id"]
    old_task, _ = service.prepare_background_batch_task("pandoc", batch_id)

    confirmed = service.confirm_batch_questions(
        batch_id,
        [{"title": "Teacher edit", "answer": "A", "analysis": "kept"}],
        expected_input_version=1,
    )

    with pytest.raises(StaleBatchVersionError):
        service.execute_background_batch_task(old_task.task_id, "pandoc", batch_id)

    status = service.get_batch_status(batch_id)
    assert status["status"] == "confirmed"
    assert status["content_version"] == 2
    assert confirmed.status == "completed"
    assert adapter.calls == 0


def test_repeated_confirmation_does_not_create_duplicate_review_task(pipeline) -> None:
    service, repository, _adapter = pipeline
    batch_id = service.create_batch_from_upload("review.md", b"question")["batch_id"]
    questions = [{"title": "Teacher edit", "answer": "A", "analysis": "kept"}]

    first = service.confirm_batch_questions(batch_id, questions)
    second = service.confirm_batch_questions(batch_id, questions)

    assert second.task_id == first.task_id
    assert len(repository.list(task_types=["import_confirmed"])) == 1
    assert service.get_batch_status(batch_id)["content_version"] == 2


def test_confirmation_persists_images_for_review_cache(pipeline) -> None:
    service, _repository, _adapter = pipeline
    batch_id = service.create_batch_from_upload("with-image.docx", b"document")["batch_id"]
    image_path = pipeline_module.default_import_batches_dir() / batch_id / "pandoc" / "media" / "diagram.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"image-bytes")
    asset = {
        "image_id": "image_0001",
        "filename": "diagram.png",
        "relative_path": str(image_path.relative_to(pipeline_module.project_root())).replace("\\", "/"),
        "absolute_path": str(image_path),
        "size": image_path.stat().st_size,
    }

    confirmed = service.confirm_batch_questions(
        batch_id,
        [{"title": "Question with a diagram", "answer": "A", "figures": []}],
        media_assets=[asset],
    )

    assert confirmed.result is not None
    assert confirmed.result["media_assets"] == [asset]
    assert service.list_batch_images(batch_id) == [asset]
    assert service.get_batch_status(batch_id)["image_count"] == 1
