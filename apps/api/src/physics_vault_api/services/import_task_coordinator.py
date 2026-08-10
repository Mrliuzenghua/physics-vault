from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, ContextManager

from ..repositories.import_tasks import ImportTask


class ImportTaskCoordinator:
    """Coordinates durable import-stage tasks without knowing parsing details."""

    SUPPORTED_OPERATIONS = frozenset({"pandoc", "ai_clean", "ai_structure", "recognize"})

    def __init__(
        self,
        *,
        task_repo: Any,
        get_task: Callable[[str], ImportTask],
        read_metadata: Callable[[str], dict[str, Any]],
        write_metadata: Callable[[str, dict[str, Any]], None],
        assert_input_version: Callable[[str, int], dict[str, Any]],
        batch_lock: Callable[[str], ContextManager[Any]],
        workspace_root: Callable[[], Path],
        sha256_file: Callable[[Path], str],
        now_iso: Callable[[], str],
        config_version: str,
    ) -> None:
        self._task_repo = task_repo
        self._get_task = get_task
        self._read_metadata = read_metadata
        self._write_metadata = write_metadata
        self._assert_input_version = assert_input_version
        self._batch_lock = batch_lock
        self._workspace_root = workspace_root
        self._sha256_file = sha256_file
        self._now_iso = now_iso
        self._config_version = config_version

    def idempotency_key(self, operation: str, batch_id: str, metadata: dict[str, Any]) -> str:
        source_hash = str(metadata.get("source_sha256") or "")
        if not source_hash:
            source_path = self._workspace_root() / str(metadata.get("source_path") or "")
            if source_path.exists():
                source_hash = self._sha256_file(source_path)
        canonical = json.dumps(
            {
                "operation": operation,
                "batch_id": batch_id,
                "input_sha256": source_hash,
                "config_version": str(metadata.get("config_version") or self._config_version),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def result_is_valid(self, operation: str, task: ImportTask) -> bool:
        if task.status != "completed" or not isinstance(task.result, dict):
            return False
        if task.result_file_path and not Path(task.result_file_path).exists():
            return False
        required_keys = {
            "pandoc": ("relative_markdown_path",),
            "ai_clean": ("relative_cleaned_markdown_path",),
            "ai_structure": ("raw_json_path", "normalized_json_path"),
        }.get(operation, ())
        for key in required_keys:
            if not self._path_exists(str(task.result.get(key) or "")):
                return False
        assets = task.result.get("media_assets") or task.result.get("images") or []
        if isinstance(assets, list):
            for asset in assets:
                if isinstance(asset, dict) and not self._path_exists(
                    str(asset.get("relative_path") or asset.get("absolute_path") or ""),
                    allow_empty=True,
                ):
                    return False
        return True

    def record_stage_checkpoint(self, batch_id: str, stage: str, task_id: str, input_version: int) -> None:
        with self._batch_lock(batch_id):
            metadata = self._assert_input_version(batch_id, input_version)
            stages = dict(metadata.get("completed_stages") or {})
            stages[stage] = {
                "task_id": task_id,
                "input_version": input_version,
                "completed_at": self._now_iso(),
            }
            metadata["completed_stages"] = stages
            metadata["updated_at"] = self._now_iso()
            self._write_metadata(batch_id, metadata)

    def cached_stage_task(self, batch_id: str, stage: str, input_version: int) -> ImportTask | None:
        metadata = self._read_metadata(batch_id)
        checkpoint = (metadata.get("completed_stages") or {}).get(stage)
        if not isinstance(checkpoint, dict) or int(checkpoint.get("input_version") or 0) != input_version:
            return None
        task_id = str(checkpoint.get("task_id") or "")
        task = self._task_repo.get(task_id) if task_id else None
        return task if task and self.result_is_valid(stage, task) else None

    def prepare_background_task(
        self,
        operation: str,
        batch_id: str,
        *,
        max_attempts: int = 1,
        request_context: dict[str, Any] | None = None,
    ) -> tuple[ImportTask, bool]:
        if operation not in self.SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported background import operation: {operation}")
        metadata = self._read_metadata(batch_id)
        input_version = max(1, int(metadata.get("content_version") or 1))
        idempotency_key = self.idempotency_key(operation, batch_id, metadata)
        summary: dict[str, Any] = {
            "batch_id": batch_id,
            "operation": operation,
            "input_version": input_version,
            "input_sha256": str(metadata.get("source_sha256") or ""),
            "config_version": str(metadata.get("config_version") or self._config_version),
        }
        if request_context:
            summary["request_context"] = {
                key: str(value)
                for key, value in request_context.items()
                if value is not None and key in {"source", "session_id", "operator"}
            }
        task, created = self._create_or_get(operation, summary, max_attempts, idempotency_key)
        should_dispatch = created
        if not created and (
            task.status in {"failed", "cancelled"}
            or (task.status == "completed" and not self.result_is_valid(operation, task))
        ):
            task, should_dispatch = self._create_or_get(
                operation,
                summary,
                max_attempts,
                f"{idempotency_key}:retry:{task.attempt + 1}",
            )
        elif not created:
            should_dispatch = False

        metadata.update(
            {
                "status": "queued" if should_dispatch else task.status,
                "active_task_id": task.task_id,
                "active_operation": operation,
                "updated_at": self._now_iso(),
            }
        )
        self._write_metadata(batch_id, metadata)
        return task, should_dispatch

    def execute_background_task(
        self,
        task_id: str,
        operation: str,
        batch_id: str,
        run_operation: Callable[[str, str, int], dict[str, Any]],
    ) -> ImportTask:
        """Claim and finalize a task while the caller supplies the domain operation."""
        current = self._get_task(task_id)
        if current.status in {"completed", "failed", "cancel_requested", "cancelled"}:
            return current
        claim = getattr(self._task_repo, "claim", None)
        if callable(claim):
            if claim(task_id, current_step=operation) is None:
                return self._get_task(task_id)
        else:
            self._task_repo.mark_running(task_id, current_step=operation, progress=max(1, current.progress))

        expected_input_version = int(current.input_summary.get("input_version") or 1)
        self._update_batch_status(
            batch_id,
            expected_input_version,
            status="running",
            task_id=task_id,
            operation=operation,
        )
        result = dict(run_operation(operation, batch_id, expected_input_version))
        result["task_id"] = task_id
        with self._batch_lock(batch_id):
            metadata = self._assert_input_version(batch_id, expected_input_version)
            metadata.update(
                {
                    "status": str(result.get("status") or "completed"),
                    "active_task_id": task_id,
                    "active_operation": operation,
                    "updated_at": self._now_iso(),
                }
            )
            self._write_metadata(batch_id, metadata)
            return self._task_repo.mark_completed(task_id, result)

    def mark_background_task_retrying(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
    ) -> ImportTask:
        task = self._get_task(task_id)
        self._update_task_batch_status(task, status="retrying", error=error)
        mark_retrying = getattr(self._task_repo, "mark_retrying", None)
        if callable(mark_retrying):
            return mark_retrying(
                task_id,
                error,
                error_type=error_type,
                user_message=user_message or "任务暂时失败，系统将自动重试",
                technical_details=technical_details or error,
            )
        return self._task_repo.mark_running(task_id)

    def fail_background_task(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
        retryable: bool = False,
    ) -> ImportTask:
        task = self._get_task(task_id)
        self._update_task_batch_status(task, status="failed", error=error)
        return self._task_repo.mark_failed(
            task_id,
            error,
            error_type=error_type,
            user_message=user_message or error,
            technical_details=technical_details or error,
            retryable=retryable,
        )

    def _create_or_get(
        self,
        operation: str,
        summary: dict[str, Any],
        max_attempts: int,
        idempotency_key: str,
    ) -> tuple[ImportTask, bool]:
        create_or_get = getattr(self._task_repo, "create_or_get", None)
        if callable(create_or_get):
            return create_or_get(
                task_type=f"background_{operation}",
                input_summary=summary,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
            )
        return (
            self._task_repo.create(
                task_type=f"background_{operation}",
                input_summary=summary,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
            ),
            True,
        )

    def _update_task_batch_status(self, task: ImportTask, *, status: str, error: str) -> None:
        batch_id = str(task.input_summary.get("batch_id") or "")
        if not batch_id:
            return
        expected_version = int(task.input_summary.get("input_version") or 1)
        metadata = self._read_metadata(batch_id)
        if max(1, int(metadata.get("content_version") or 1)) != expected_version:
            return
        metadata.update(
            {
                "status": status,
                "active_task_id": task.task_id,
                "error": error,
                "updated_at": self._now_iso(),
            }
        )
        self._write_metadata(batch_id, metadata)

    def _update_batch_status(
        self,
        batch_id: str,
        expected_input_version: int,
        *,
        status: str,
        task_id: str,
        operation: str,
    ) -> None:
        with self._batch_lock(batch_id):
            metadata = self._assert_input_version(batch_id, expected_input_version)
            metadata.update(
                {
                    "status": status,
                    "active_task_id": task_id,
                    "active_operation": operation,
                    "updated_at": self._now_iso(),
                }
            )
            self._write_metadata(batch_id, metadata)

    def _path_exists(self, raw_path: str, *, allow_empty: bool = False) -> bool:
        if not raw_path:
            return allow_empty
        path = Path(raw_path)
        candidate = path if path.is_absolute() else self._workspace_root() / path
        return candidate.exists()
