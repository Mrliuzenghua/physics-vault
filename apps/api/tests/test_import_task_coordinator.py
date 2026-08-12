from contextlib import nullcontext
from pathlib import Path

from physics_vault_api.repositories.import_tasks import InMemoryImportTaskRepository
from physics_vault_api.services.import_task_coordinator import ImportTaskCoordinator


def test_prepare_background_task_reuses_idempotent_pending_task(tmp_path: Path) -> None:
    metadata = {
        "batch_id": "batch-1",
        "content_version": 1,
        "source_sha256": "a" * 64,
        "completed_stages": {},
    }
    repository = InMemoryImportTaskRepository()

    coordinator = ImportTaskCoordinator(
        task_repo=repository,
        get_task=lambda task_id: repository.get(task_id),  # type: ignore[return-value]
        read_metadata=lambda _batch_id: dict(metadata),
        write_metadata=lambda _batch_id, updated: metadata.update(updated),
        assert_input_version=lambda _batch_id, version: dict(metadata) if version == 1 else {},
        batch_lock=lambda _batch_id: nullcontext(),
        workspace_root=lambda: tmp_path,
        sha256_file=lambda _path: "unused",
        now_iso=lambda: "2026-08-10T00:00:00",
        config_version="1",
    )

    first, first_should_dispatch = coordinator.prepare_background_task("pandoc", "batch-1")
    second, second_should_dispatch = coordinator.prepare_background_task("pandoc", "batch-1")

    assert first.task_id == second.task_id
    assert first_should_dispatch is True
    assert second_should_dispatch is False
    assert metadata["active_operation"] == "pandoc"


def test_explicit_operation_id_replays_failed_task_without_implicit_retry(tmp_path: Path) -> None:
    metadata = {"batch_id": "batch-1", "content_version": 1, "source_sha256": "b" * 64}
    repository = InMemoryImportTaskRepository()
    coordinator = ImportTaskCoordinator(
        task_repo=repository,
        get_task=lambda task_id: repository.get(task_id),  # type: ignore[return-value]
        read_metadata=lambda _batch_id: dict(metadata),
        write_metadata=lambda _batch_id, updated: metadata.update(updated),
        assert_input_version=lambda _batch_id, version: dict(metadata) if version == 1 else {},
        batch_lock=lambda _batch_id: nullcontext(),
        workspace_root=lambda: tmp_path,
        sha256_file=lambda _path: "unused",
        now_iso=lambda: "2026-08-10T00:00:00",
        config_version="1",
    )

    first, _ = coordinator.prepare_background_task(
        "pandoc", "batch-1", idempotency_key="mcp-operation:fixed-request"
    )
    repository.mark_failed(first.task_id, "failed")
    replay, should_dispatch = coordinator.prepare_background_task(
        "pandoc", "batch-1", idempotency_key="mcp-operation:fixed-request"
    )

    assert replay.task_id == first.task_id
    assert replay.status == "failed"
    assert should_dispatch is False
    assert len(repository.list(limit=10)) == 1
