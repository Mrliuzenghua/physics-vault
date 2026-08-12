"""Registration boundary for the management and governance MCP domain (MCP-105)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from ..tool_registry import ToolDomain, ToolRegistry

ToolHandler = Callable[..., Any]
ToolDecoratorFactory = Callable[[], Callable[[ToolHandler], ToolHandler]]


class ManagementDomain:
    """Compatibility facade for metadata maintenance and governance MCP tools.

    Existing handlers remain injected from the entrypoint, preserving all dry-run,
    confirmation, reason and audit semantics while registration leaves the monolith.
    """

    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        self._handlers = handlers

    def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._handlers[name](*args, **kwargs)

    def create_knowledge_points(self, points: list[dict[str, Any]]) -> dict[str, Any]:
        return self._call("create_knowledge_points", points)

    def organize_knowledge_tree(self, assignments: list[dict[str, Any]], task_id: str | None=None, reason: str | None=None) -> dict[str, Any]:
        return self._call("organize_knowledge_tree", assignments, task_id, reason)

    def batch_update_question_metadata(self, updates: list[dict[str, Any]], reason: str | None=None) -> dict[str, Any]:
        return self._call("batch_update_question_metadata", updates, reason)

    def diagnose_tag_maintenance(self, query: str | None=None, limit: int=50, min_similarity: float=0.86) -> dict[str, Any]:
        return self._call("diagnose_tag_maintenance", query, limit, min_similarity)

    def suggest_question_tags(self, question_ids: list[str]) -> dict[str, Any]:
        return self._call("suggest_question_tags", question_ids)

    def maintain_question_tags(self, question_ids: list[str] | None=None, add_tags: list[str] | None=None, remove_tags: list[str] | None=None, merge_map: dict[str, list[str]] | None=None, dry_run: bool=True, reason: str | None=None, create_catalog_tags: bool=True) -> dict[str, Any]:
        return self._call("maintain_question_tags", question_ids, add_tags, remove_tags, merge_map, dry_run, reason, create_catalog_tags)

    def record_method_retrieval_feedback(self, question_id: str, method_query: str, verdict: Literal['correct', 'incorrect', 'missed'], branch: Literal['gravity', 'electric'] | None=None, reason: str | None=None, maintain_metadata: bool=True, operator: str='teacher') -> dict[str, Any]:
        return self._call("record_method_retrieval_feedback", question_id, method_query, verdict, branch, reason, maintain_metadata, operator)

    def maintain_question_knowledge_points(self, question_ids: list[str], auto_fix: bool=True, reason: str | None=None) -> dict[str, Any]:
        return self._call("maintain_question_knowledge_points", question_ids, auto_fix, reason)

    def backfill_canonical_question_hashes(self, dry_run: bool=True, reason: str='为正式题库建立重复题内容指纹', overwrite_existing: bool=False) -> dict[str, Any]:
        return self._call("backfill_canonical_question_hashes", dry_run, reason, overwrite_existing)

    def merge_canonical_duplicate_questions(self, primary_question_id: str, duplicate_question_ids: list[str], dry_run: bool=True, reason: str='合并正式题库完全重复题', plan_token: str | None=None) -> dict[str, Any]:
        args = (primary_question_id, duplicate_question_ids, dry_run, reason)
        return self._call("merge_canonical_duplicate_questions", *args, plan_token) if plan_token is not None else self._call("merge_canonical_duplicate_questions", *args)

    def restore_canonical_duplicate_merge(self, merge_batch_id: str, dry_run: bool=True, reason: str='恢复重复题合并', plan_token: str | None=None) -> dict[str, Any]:
        args = (merge_batch_id, dry_run, reason)
        return self._call("restore_canonical_duplicate_merge", *args, plan_token) if plan_token is not None else self._call("restore_canonical_duplicate_merge", *args)

    def batch_replace_question_tags(self, updates: list[dict[str, Any]], dry_run: bool=True, reason: str | None=None) -> dict[str, Any]:
        return self._call("batch_replace_question_tags", updates, dry_run, reason)

    def batch_replace_question_knowledge_points(self, updates: list[dict[str, Any]], dry_run: bool=True, reason: str | None=None) -> dict[str, Any]:
        return self._call("batch_replace_question_knowledge_points", updates, dry_run, reason)

    def return_question_to_review(self, question_id: str, reason: str='题目需要回炉重造', dry_run: bool=True, operation_id: str | None=None, plan_token: str | None=None) -> dict[str, Any]:
        args = (question_id, reason, dry_run, operation_id)
        return self._call("return_question_to_review", *args, plan_token) if plan_token is not None else self._call("return_question_to_review", *args)

    def reconcile_review_queue_outbox(self, limit: int=20) -> dict[str, Any]:
        return self._call("reconcile_review_queue_outbox", limit)

    def list_change_batches(self, change_type: str | None=None, status: str | None=None, limit: int=50) -> dict[str, Any]:
        return self._call("list_change_batches", change_type, status, limit)

    def get_change_batch(self, batch_id: str) -> dict[str, Any]:
        return self._call("get_change_batch", batch_id)

    def rollback_change_batch(self, batch_id: str, dry_run: bool=True, reason: str | None=None, allow_conflicts: bool=False, plan_token: str | None=None) -> dict[str, Any]:
        args = (batch_id, dry_run, reason, allow_conflicts)
        return self._call("rollback_change_batch", *args, plan_token) if plan_token is not None else self._call("rollback_change_batch", *args)


def management_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    """Return compatible MCP-105 names in catalogue order."""
    return tuple(spec.name for spec in registry.discover(domain=ToolDomain.MANAGEMENT))


def register_management_tools(
    tool: ToolDecoratorFactory,
    registry: ToolRegistry,
    handlers: Mapping[str, ToolHandler],
) -> tuple[str, ...]:
    """Bind all and only declared MCP-105 handlers to the MCP transport."""
    names = management_tool_names(registry)
    missing = [name for name in names if not callable(handlers.get(name))]
    if missing:
        raise RuntimeError(f"MCP-105 handlers are missing: {', '.join(missing)}")
    for name in names:
        tool()(handlers[name])
    return names
