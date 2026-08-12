"""Registration boundary for the catalog search and knowledge MCP domain.

Handlers remain compatibility facades in the monolithic entrypoint during the
incremental migration. This module owns which declared tools form MCP-101 and
makes omissions fail while the server is assembled.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from ..tool_registry import ToolDomain, ToolRegistry


ToolHandler = Callable[..., Any]
ToolDecoratorFactory = Callable[[], Callable[[ToolHandler], ToolHandler]]


class SearchKnowledgeDomain:
    """Compatibility-preserving MCP-101 handler surface.

    The entrypoint supplies existing implementations as dependencies while this
    domain owns the public signatures exposed through the MCP transport.
    """

    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        self._handlers = handlers

    def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._handlers[name](*args, **kwargs)

    def list_filter_facets(self) -> dict[str, Any]: return self._call("list_filter_facets")

    def search_questions(self, query: str | None = None, search_mode: Literal["browse", "strict", "hybrid", "similar", "comprehensive"] = "hybrid", question_type: str | None = None, difficulty: str | None = None, status: str | None = None, year: int | None = None, module: str | None = None, topic1_id: str | None = None, topic2_id: str | None = None, topic3_id: str | None = None, topic2: str | None = None, topic3: str | None = None, region: str | None = None, exam_type: str | None = None, has_media: bool | None = None, image_count_min: int = 0, is_mistake: bool | None = None, limit: int = 12, offset: int = 0) -> dict[str, Any]:
        return self._call("search_questions", query, search_mode, question_type, difficulty, status, year, module, topic1_id, topic2_id, topic3_id, topic2, topic3, region, exam_type, has_media, image_count_min, is_mistake, limit, offset)

    def search_questions_compact(self, query: str | None = None, search_mode: Literal["browse", "strict", "hybrid", "similar", "comprehensive"] = "hybrid", question_type: str | None = None, difficulty: str | None = None, year: int | None = None, topic3_id: str | None = None, limit: int = 12, offset: int = 0) -> dict[str, Any]:
        return self._call("search_questions_compact", query, search_mode, question_type, difficulty, year, topic3_id, limit, offset)

    def search_questions_curated(self, query: str, target_count: int = 10, candidate_limit: int = 50, search_mode: Literal["strict", "hybrid", "comprehensive"] = "hybrid", question_type: str | None = None, difficulty: str | None = None, year: int | None = None, topic3_id: str | None = None) -> dict[str, Any]:
        return self._call("search_questions_curated", query, target_count, candidate_limit, search_mode, question_type, difficulty, year, topic3_id)

    def download_question_images(self, question_id: str, destination_subdir: str | None = None, overwrite: bool = False) -> dict[str, Any]: return self._call("download_question_images", question_id, destination_subdir, overwrite)
    def search_topic_questions(self, query: str, question_type: str | None = None, difficulty: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]: return self._call("search_topic_questions", query, question_type, difficulty, limit, offset)
    def search_method_questions(self, query: str, year: int | None = None, region: str | None = None, question_type: str | None = None, difficulty: str | None = None, limit: int = 20, offset: int = 0, summary_only: bool = True, include_evidence: bool = False, confirmed_only: bool = True) -> dict[str, Any]: return self._call("search_method_questions", query, year, region, question_type, difficulty, limit, offset, summary_only, include_evidence, confirmed_only)
    def list_method_retrieval_feedback(self, question_id: str | None = None, limit: int = 100) -> dict[str, Any]: return self._call("list_method_retrieval_feedback", question_id, limit)
    def method_retrieval_learning_report(self, limit: int = 50) -> dict[str, Any]: return self._call("method_retrieval_learning_report", limit)
    def get_questions_by_ids(self, question_ids: list[str]) -> dict[str, Any]: return self._call("get_questions_by_ids", question_ids)
    def list_knowledge_tree(self, keyword: str | None = None, limit: int = 200) -> dict[str, Any]: return self._call("list_knowledge_tree", keyword, limit)
    def search_knowledge_points(self, keyword: str, limit: int = 20) -> dict[str, Any]: return self._call("search_knowledge_points", keyword, limit)
    def get_question_knowledge_points(self, question_id: str) -> dict[str, Any]: return self._call("get_question_knowledge_points", question_id)
    def database_boundary_report(self) -> dict[str, Any]: return self._call("database_boundary_report")
    def database_health_report(self) -> dict[str, Any]: return self._call("database_health_report")
    def list_question_tags(self, query: str | None = None, question_ids: list[str] | None = None, limit: int = 200) -> dict[str, Any]: return self._call("list_question_tags", query, question_ids, limit)
    def find_similar_questions(self, question_id: str, limit: int = 10, same_question_type: bool = False, same_knowledge_point: bool = False, difficulty_tolerance: int = 99) -> dict[str, Any]: return self._call("find_similar_questions", question_id, limit, same_question_type, same_knowledge_point, difficulty_tolerance)
    def scan_canonical_duplicate_questions(self, limit: int = 100) -> dict[str, Any]: return self._call("scan_canonical_duplicate_questions", limit)
    def list_canonical_duplicate_merges(self, state: Literal["archived", "restored", "all"] = "archived", limit: int = 50) -> dict[str, Any]: return self._call("list_canonical_duplicate_merges", state, limit)
    def get_workflow_guide(self, intent: str | None = None) -> dict[str, Any]: return self._call("get_workflow_guide", intent)
    def mcp_system_health(self, include_details: bool = False) -> dict[str, Any]: return self._call("mcp_system_health", include_details)


def search_knowledge_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    """Return the compatible MCP-101 public names in catalogue order."""
    return tuple(spec.name for spec in registry.discover(domain=ToolDomain.SEARCH))


def register_search_knowledge_tools(
    tool: ToolDecoratorFactory,
    registry: ToolRegistry,
    handlers: Mapping[str, ToolHandler],
) -> tuple[str, ...]:
    """Bind all and only the declared MCP-101 handlers to the MCP transport."""
    names = search_knowledge_tool_names(registry)
    missing = [name for name in names if not callable(handlers.get(name))]
    if missing:
        raise RuntimeError(f"MCP-101 handlers are missing: {', '.join(missing)}")
    for name in names:
        tool()(handlers[name])
    return names
