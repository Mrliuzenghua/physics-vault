from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from ..paths import project_root
from ..repositories.import_tasks import ImportTask
from ..schemas.lesson_exports import LessonExportRequest
from .document_pipeline import ImportPipelineService
from .task_queue import ImportTaskDispatcher

if TYPE_CHECKING:
    from .lesson_exports import LessonExportService
    from .task_queue import LessonExportDispatcher


ACTIVE_STATUSES = {"pending", "running", "retrying", "cancel_requested"}
TERMINAL_STATUSES = {"cancelled", "completed", "failed"}

TASK_TYPE_NAMES = {
    "background_pandoc": "文档转换",
    "background_ai_clean": "AI 清洗",
    "background_ai_structure": "AI 结构化",
    "background_recognize": "导入识别",
    "convert_document": "文档转换",
    "clean_document": "文档清洗",
    "parse_structured_questions": "题目结构化",
    "ai_parse_document": "AI 文档识别",
    "ai_generated_review": "AI 生成送审",
    "ai_generated_knowledge_review": "知识点生成送审",
    "import_confirmed": "导入校对",
    "pandoc_unpack": "文档转换",
    "ai_clean_markdown": "AI 清洗",
    "ai_structure_questions": "AI 结构化",
    "word_export": "Word 导出",
    "pptx_export": "PPT 导出",
}

STEP_NAMES = {
    "pandoc": "转换文档",
    "ai_clean": "AI 清洗",
    "ai_structure": "整理题目结构",
    "recognize": "识别题目",
}


@dataclass(frozen=True, slots=True)
class TaskActionContext:
    source: str = "physics_vault_mcp"
    session_id: str | None = None
    operator: str = "MCP user"
    confirmed: bool = False

    def as_request_context(self) -> dict[str, str]:
        values = {
            "source": self.source.strip() or "physics_vault_mcp",
            "session_id": (self.session_id or "").strip(),
            "operator": self.operator.strip() or "MCP user",
        }
        return {key: value for key, value in values.items() if value}


class TaskCenterService:
    def __init__(
        self,
        import_service: ImportPipelineService,
        dispatcher: ImportTaskDispatcher | None = None,
        lesson_export_service: LessonExportService | None = None,
        export_dispatcher: LessonExportDispatcher | None = None,
    ) -> None:
        self._import_service = import_service
        self._repository = import_service._task_repo
        self._dispatcher = dispatcher or ImportTaskDispatcher(import_service)
        self._lesson_export_service = lesson_export_service
        if export_dispatcher is not None:
            self._export_dispatcher = export_dispatcher
        elif lesson_export_service is not None:
            from .task_queue import LessonExportDispatcher

            self._export_dispatcher = LessonExportDispatcher(lesson_export_service)
        else:
            self._export_dispatcher = None

    def list_tasks(
        self,
        *,
        statuses: list[str] | None,
        task_types: list[str] | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if created_from is not None and created_from.tzinfo is None:
            created_from = created_from.replace(tzinfo=UTC)
        if created_to is not None and created_to.tzinfo is None:
            created_to = created_to.replace(tzinfo=UTC)
        offset = (page - 1) * page_size
        list_page = getattr(self._repository, "list_page", None)
        if callable(list_page):
            tasks, total = list_page(
                statuses=statuses,
                task_types=task_types,
                created_from=created_from,
                created_to=created_to,
                offset=offset,
                limit=page_size,
            )
        else:
            tasks: list[ImportTask] = []
            scan_offset = 0
            while True:
                batch = self._repository.list(
                    limit=200,
                    task_types=task_types,
                    statuses=statuses,
                    offset=scan_offset,
                )
                tasks.extend(batch)
                if len(batch) < 200:
                    break
                scan_offset += len(batch)
            if created_from:
                tasks = [task for task in tasks if task.created_at >= created_from]
            if created_to:
                tasks = [task for task in tasks if task.created_at <= created_to]
            total = len(tasks)
            tasks = tasks[offset : offset + page_size]
        return [self.serialize(task) for task in tasks], total

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.serialize(self._import_service.get_task(task_id))

    def submit_batch_job(
        self,
        operation: str,
        batch_id: str,
        *,
        context: TaskActionContext,
    ) -> tuple[dict[str, Any], str]:
        if operation not in {"recognize", "ai_clean"}:
            raise HTTPException(status_code=400, detail=f"Unsupported MCP task operation: {operation}")
        task = self._dispatcher.submit_batch_stage(
            operation,
            batch_id,
            request_context=context.as_request_context(),
        )
        audit_id = self._record_action(
            task.task_id,
            f"submit_{operation}",
            context,
            {"batch_id": batch_id, "task_status": task.status},
        )
        return self.serialize(task), audit_id

    def submit_export_job(
        self,
        export_format: str,
        lesson_package: dict[str, Any],
        *,
        include_answers: bool,
        include_analysis: bool,
        file_name: str | None,
        context: TaskActionContext,
        answer_position: str = "after_question",
    ) -> tuple[dict[str, Any], str]:
        if export_format not in {"word", "pptx"}:
            raise HTTPException(status_code=400, detail=f"Unsupported export format: {export_format}")
        if self._export_dispatcher is None:
            raise HTTPException(status_code=503, detail="服务端导出暂不可用")
        payload = LessonExportRequest(
            lesson_package=lesson_package,
            include_answers=include_answers,
            include_analysis=include_analysis,
            answer_position=answer_position,  # type: ignore[arg-type]
            file_name=file_name,
        )
        task = self._export_dispatcher.submit(
            export_format,
            payload,
            request_context=context.as_request_context(),
        )
        audit_id = self._record_action(
            task.task_id,
            f"submit_{export_format}_export",
            context,
            {
                "lesson_id": str(lesson_package.get("id") or ""),
                "task_status": task.status,
            },
        )
        return self.serialize(task), audit_id

    def retry_job(
        self,
        task_id: str,
        *,
        context: TaskActionContext,
    ) -> tuple[dict[str, Any], str, str]:
        if not context.confirmed:
            raise HTTPException(status_code=409, detail="Retry requires explicit confirmation")
        task, original_task_id = self.retry_task(task_id)
        audit_id = self._record_action(
            task["task_id"],
            "retry",
            context,
            {"original_task_id": original_task_id},
        )
        return task, original_task_id, audit_id

    def cancel_job(
        self,
        task_id: str,
        *,
        context: TaskActionContext,
    ) -> tuple[dict[str, Any], str]:
        if not context.confirmed:
            raise HTTPException(status_code=409, detail="Cancellation requires explicit confirmation")
        task = self.cancel_task(task_id)
        audit_id = self._record_action(
            task_id,
            "cancel",
            context,
            {"resulting_status": task["status"]},
        )
        return task, audit_id

    def retry_task(self, task_id: str) -> tuple[dict[str, Any], str]:
        original = self._import_service.get_task(task_id)
        if original.status not in {"failed", "cancelled"}:
            raise HTTPException(status_code=409, detail="只有失败或已取消的任务可以重试")
        if original.task_type in {"word_export", "pptx_export"}:
            if self._export_dispatcher is None:
                raise HTTPException(status_code=503, detail="导出重试服务暂不可用")
            try:
                retried = self._export_dispatcher.retry(task_id)
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return self.serialize(retried), original.task_id
        operation = str(original.input_summary.get("operation") or "")
        batch_id = str(original.input_summary.get("batch_id") or "")
        if not operation or not batch_id or not original.task_type.startswith("background_"):
            raise HTTPException(status_code=409, detail="此任务暂不支持自动重试，请回到原业务页面重新提交")
        retried = self._dispatcher.submit_batch_stage(operation, batch_id)
        return self.serialize(retried), original.task_id

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        task = self._import_service.get_task(task_id)
        if task.status in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="任务已经结束，无法取消")
        request_cancel = getattr(self._repository, "request_cancel", None)
        if not callable(request_cancel):
            raise HTTPException(status_code=503, detail="当前任务存储不支持取消操作")
        return self.serialize(request_cancel(task_id))

    def _record_action(
        self,
        task_id: str,
        action: str,
        context: TaskActionContext,
        details: dict[str, Any],
    ) -> str:
        recorder = getattr(self._repository, "record_action_audit", None)
        if not callable(recorder):
            raise HTTPException(status_code=503, detail="Task action audit storage is unavailable")
        audit = recorder(
            task_id,
            action,
            source=context.source.strip() or "physics_vault_mcp",
            session_id=(context.session_id or "").strip() or None,
            operator=context.operator.strip() or "MCP user",
            confirmed=context.confirmed,
            details=details,
        )
        return str(audit.audit_id)

    def resolve_result_file(self, task_id: str) -> tuple[Path, str]:
        task = self._import_service.get_task(task_id)
        if task.status != "completed":
            raise HTTPException(status_code=409, detail="任务尚未完成，暂无可下载结果")
        if task.task_type in {"word_export", "pptx_export"} and self._lesson_export_service is not None:
            try:
                resolved = self._lesson_export_service.resolve_result_file(task_id)
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(status_code=404, detail="结果文件不存在或已过期") from exc
            return resolved, resolved.name
        path = self._result_path(task)
        if path is None:
            raise HTTPException(status_code=404, detail="此任务没有可下载的结果文件")
        root = project_root().resolve()
        resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise HTTPException(status_code=404, detail="结果文件不存在或已过期")
        return resolved, resolved.name

    def serialize(self, task: ImportTask) -> dict[str, Any]:
        summary = dict(task.input_summary or {})
        result = dict(task.result or {}) if task.result else None
        operation = str(summary.get("operation") or "")
        progress = self._progress(task, result)
        current_step = str(
            getattr(task, "current_step", "")
            or (result or {}).get("current_step")
            or summary.get("current_step")
            or STEP_NAMES.get(operation)
            or self._default_step(task.status)
        )
        started_at = getattr(task, "started_at", None)
        if started_at is None and task.status != "pending":
            started_at = task.updated_at if task.status in ACTIVE_STATUSES else task.created_at
        finished_at = getattr(task, "finished_at", None)
        if finished_at is None and task.status in TERMINAL_STATUSES:
            finished_at = task.updated_at
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "task_name": self._task_name(task),
            "status": task.status,
            "progress": progress,
            "current_step": current_step,
            "attempt": int(getattr(task, "attempt", summary.get("attempt", 0)) or 0),
            "max_attempts": int(getattr(task, "max_attempts", summary.get("max_attempts", 1)) or 1),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "started_at": started_at,
            "finished_at": finished_at,
            "result_available": self._result_path(task) is not None,
            "error": self._error_info(task),
            "input_summary": summary,
            "result_summary": self._compact_result(result),
        }

    @staticmethod
    def _progress(task: ImportTask, result: dict[str, Any] | None) -> int:
        if task.status == "completed":
            return 100
        raw = getattr(task, "progress", None)
        if raw is None:
            raw = (result or {}).get("progress")
        if raw is None:
            raw = 100 if task.status in TERMINAL_STATUSES else (50 if task.status in {"running", "retrying", "cancel_requested"} else 0)
        try:
            return max(0, min(100, int(raw)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _default_step(status: str) -> str:
        return {
            "pending": "等待处理",
            "running": "正在处理",
            "retrying": "等待重试",
            "cancel_requested": "正在取消",
            "cancelled": "已取消",
            "completed": "处理完成",
            "failed": "处理失败",
        }.get(status, "")

    @staticmethod
    def _task_name(task: ImportTask) -> str:
        summary = task.input_summary or {}
        source = summary.get("original_filename") or summary.get("source") or summary.get("filename")
        base = TASK_TYPE_NAMES.get(task.task_type, task.task_type.replace("_", " "))
        return f"{base} · {source}" if source else base

    @staticmethod
    def _error_info(task: ImportTask) -> dict[str, Any] | None:
        structured = getattr(task, "error_info", None)
        if structured is not None:
            return {
                "error_type": str(structured.error_type),
                "user_message": TaskCenterService._friendly_error_message(str(structured.message)),
                "technical_detail": structured.technical_details,
                "retryable": bool(structured.retryable),
            }
        if not task.error:
            return None
        raw = str(task.error)
        parsed: dict[str, Any] = {}
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                parsed = value
        except json.JSONDecodeError:
            pass
        return {
            "error_type": str(parsed.get("error_type") or parsed.get("type") or "task_error"),
            "user_message": str(parsed.get("user_message") or parsed.get("message") or "任务执行失败，请检查输入内容或稍后重试。"),
            "technical_detail": str(parsed.get("technical_detail") or parsed.get("detail") or raw),
            "retryable": bool(parsed.get("retryable", task.task_type.startswith("background_"))),
        }

    @staticmethod
    def _friendly_error_message(message: str) -> str:
        technical_markers = (
            "traceback",
            "unexpected keyword",
            "exception",
            "errno",
            "stack trace",
        )
        if any(marker in message.lower() for marker in technical_markers):
            return "任务执行失败，请检查输入内容或稍后重试。"
        return message

    @staticmethod
    def _result_path(task: ImportTask) -> Path | None:
        raw = getattr(task, "result_file_path", None)
        result = task.result or {}
        if not raw:
            for key in ("result_file_path", "download_path", "output_path", "archive_path"):
                candidate = result.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    raw = candidate
                    break
        return Path(str(raw)) if raw else None

    @staticmethod
    def _compact_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
        if not result:
            return None
        allowed = {
            "batch_id",
            "question_count",
            "knowledge_count",
            "image_count",
            "output_path",
            "result_file_path",
            "filename",
            "status",
            "export_format",
            "mime_type",
            "size",
            "download_url",
        }
        return {key: value for key, value in result.items() if key in allowed}
