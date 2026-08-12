"""Registration boundary for the import and review MCP domain (MCP-102)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..tool_registry import ToolDomain, ToolRegistry


ToolHandler = Callable[..., Any]
ToolDecoratorFactory = Callable[[], Callable[[ToolHandler], ToolHandler]]


class ImportReviewDomain:
    """Compatibility-preserving MCP-102 public handler surface.

    The monolithic MCP entrypoint supplies legacy implementations as injected
    handlers while this module owns the public tool signatures and domain
    registration. This keeps the review workspace separate from the canonical
    question database: handlers may create or update review drafts, but do not
    promote questions into the canonical database.
    """

    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        self._handlers = handlers

    def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._handlers[name](*args, **kwargs)

    def list_review_queue(self, status: str | None = "pending", queue_type: str | None = None, include_orphans: bool = False, limit: int = 50) -> dict[str, Any]:
        return self._call("list_review_queue", status, queue_type, include_orphans, limit)

    def import_word_folder_to_review(self, folder_path: str, recursive: bool = False, dry_run: bool = True, use_ai_cleanup: bool = True, max_files: int = 20, max_file_size_mb: int = 30, file_filter: str | None = None, skip_if_duplicate: bool = True) -> dict[str, Any]:
        return self._call("import_word_folder_to_review", folder_path, recursive, dry_run, use_ai_cleanup, max_files, max_file_size_mb, file_filter, skip_if_duplicate)

    def list_review_tasks(self, status: str | None = None, task_type: str | None = None, question_count: int | None = None, knowledge_count: int | None = None, keyword: str | None = None, reviewable_only: bool = True, limit: int = 80) -> dict[str, Any]:
        return self._call("list_review_tasks", status, task_type, question_count, knowledge_count, keyword, reviewable_only, limit)

    def get_review_task(self, task_id: str, content_limit: int = 20) -> dict[str, Any]:
        return self._call("get_review_task", task_id, content_limit)

    def get_review_task_full(self, task_id: str, question_ids: list[str] | None = None, include_knowledge: bool = True) -> dict[str, Any]:
        return self._call("get_review_task_full", task_id, question_ids, include_knowledge)

    def validate_review_task(self, task_id: str, question_ids: list[str] | None = None, require_knowledge: bool = True, require_source: bool = True, risks_only: bool = False) -> dict[str, Any]:
        return self._call("validate_review_task", task_id, question_ids, require_knowledge, require_source, risks_only)

    def find_duplicate_review_tasks(self, task_type: str | None = None, source: str | None = None, limit: int = 200) -> dict[str, Any]:
        return self._call("find_duplicate_review_tasks", task_type, source, limit)

    def delete_review_tasks(self, task_ids: list[str], confirmed: bool = False) -> dict[str, Any]:
        return self._call("delete_review_tasks", task_ids, confirmed)

    def suggest_knowledge_points_for_task(self, task_id: str, question_ids: list[str] | None = None, max_suggestions: int = 3) -> dict[str, Any]:
        return self._call("suggest_knowledge_points_for_task", task_id, question_ids, max_suggestions)

    def clean_review_task_latex(self, task_id: str, question_ids: list[str] | None = None, dry_run: bool = True, reason: str | None = None, expected_updated_at: str | None = None, plan_token: str | None = None) -> dict[str, Any]:
        return self._call("clean_review_task_latex", task_id, question_ids, dry_run, reason, expected_updated_at, plan_token)

    def split_merged_options(self, task_id: str, question_ids: list[str] | None = None, dry_run: bool = True, reason: str | None = None, expected_updated_at: str | None = None, plan_token: str | None = None) -> dict[str, Any]:
        return self._call("split_merged_options", task_id, question_ids, dry_run, reason, expected_updated_at, plan_token)

    def deduplicate_review_task_questions(self, task_id: str, dry_run: bool = True, reason: str | None = None, expected_updated_at: str | None = None, plan_token: str | None = None) -> dict[str, Any]:
        return self._call("deduplicate_review_task_questions", task_id, dry_run, reason, expected_updated_at, plan_token)

    def update_review_task_draft(self, task_id: str, updates: list[dict[str, Any]], dry_run: bool = True, reason: str | None = None, expected_updated_at: str | None = None, plan_token: str | None = None) -> dict[str, Any]:
        return self._call("update_review_task_draft", task_id, updates, dry_run, reason, expected_updated_at, plan_token)

    def submit_ai_generated_review(self, source_text: str, source: str = "Claude Code MCP", chat_context: str | None = None, session_id: str | None = None, confirmed: bool = False) -> dict[str, Any]:
        return self._call("submit_ai_generated_review", source_text, source, chat_context, session_id, confirmed)


def import_review_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    """Return the compatible MCP-102 public names in catalogue order."""
    return tuple(spec.name for spec in registry.discover(domain=ToolDomain.REVIEW))


def register_import_review_tools(
    tool: ToolDecoratorFactory,
    registry: ToolRegistry,
    handlers: Mapping[str, ToolHandler],
) -> tuple[str, ...]:
    """Bind all and only declared MCP-102 handlers to the MCP transport."""
    names = import_review_tool_names(registry)
    missing = [name for name in names if not callable(handlers.get(name))]
    if missing:
        raise RuntimeError(f"MCP-102 handlers are missing: {', '.join(missing)}")
    for name in names:
        tool()(handlers[name])
    return names
