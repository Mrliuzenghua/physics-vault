"""Registration boundary for the export and task MCP domain (MCP-104)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from ..tool_registry import ToolDomain, ToolRegistry

ToolHandler = Callable[..., Any]
ToolDecoratorFactory = Callable[[], Callable[[ToolHandler], ToolHandler]]


class OperationsDomain:
    """Compatibility facade for task submission and task-status MCP tools.

    The entrypoint injects existing handlers, so task-service execution, trace
    propagation and audit behavior remain exactly in the legacy implementations.
    """

    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        self._handlers = handlers

    def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._handlers[name](*args, **kwargs)

    def submit_import_job(self, batch_id: str, source: str='physics_vault_mcp', session_id: str | None=None, operator: str='MCP user', trace_id: str | None=None, operation_id: str | None=None, confirmed: bool=False) -> dict[str, Any]:
        return self._call("submit_import_job", batch_id, source, session_id, operator, trace_id, operation_id, confirmed)

    def submit_ai_clean_job(self, batch_id: str, source: str='physics_vault_mcp', session_id: str | None=None, operator: str='MCP user', trace_id: str | None=None, operation_id: str | None=None, confirmed: bool=False) -> dict[str, Any]:
        return self._call("submit_ai_clean_job", batch_id, source, session_id, operator, trace_id, operation_id, confirmed)

    def submit_word_export_job(self, lesson_package: dict[str, Any], include_answers: bool | None=None, include_analysis: bool | None=None, file_name: str | None=None, template_id: str | None=None, format_spec: dict[str, Any] | None=None, answer_position: Literal['after_question', 'end'] | None=None, source: str='physics_vault_mcp', session_id: str | None=None, operator: str='MCP user', trace_id: str | None=None, operation_id: str | None=None, confirmed: bool=False) -> dict[str, Any]:
        return self._call("submit_word_export_job", lesson_package, include_answers, include_analysis, file_name, template_id, format_spec, answer_position, source, session_id, operator, trace_id, operation_id, confirmed)

    def submit_pptx_export_job(self, lesson_package: dict[str, Any], include_answers: bool=False, include_analysis: bool=False, file_name: str | None=None, source: str='physics_vault_mcp', session_id: str | None=None, operator: str='MCP user', trace_id: str | None=None, operation_id: str | None=None, confirmed: bool=False) -> dict[str, Any]:
        return self._call("submit_pptx_export_job", lesson_package, include_answers, include_analysis, file_name, source, session_id, operator, trace_id, operation_id, confirmed)

    def get_job_status(self, task_id: str) -> dict[str, Any]:
        return self._call("get_job_status", task_id)

    def list_jobs(self, statuses: list[str] | None=None, task_types: list[str] | None=None, created_from: str | None=None, created_to: str | None=None, page: int=1, page_size: int=20) -> dict[str, Any]:
        return self._call("list_jobs", statuses, task_types, created_from, created_to, page, page_size)

    def retry_job(self, task_id: str, confirmed: bool=False, source: str='physics_vault_mcp', session_id: str | None=None, operator: str='MCP user', trace_id: str | None=None) -> dict[str, Any]:
        return self._call("retry_job", task_id, confirmed, source, session_id, operator, trace_id)

    def cancel_job(self, task_id: str, confirmed: bool=False, source: str='physics_vault_mcp', session_id: str | None=None, operator: str='MCP user', trace_id: str | None=None) -> dict[str, Any]:
        return self._call("cancel_job", task_id, confirmed, source, session_id, operator, trace_id)


def operations_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    """Return compatible MCP-104 names in catalogue order."""
    return tuple(spec.name for spec in registry.discover(domain=ToolDomain.OPERATIONS))


def register_operations_tools(
    tool: ToolDecoratorFactory,
    registry: ToolRegistry,
    handlers: Mapping[str, ToolHandler],
) -> tuple[str, ...]:
    """Bind all and only declared MCP-104 handlers to the MCP transport."""
    names = operations_tool_names(registry)
    missing = [name for name in names if not callable(handlers.get(name))]
    if missing:
        raise RuntimeError(f"MCP-104 handlers are missing: {', '.join(missing)}")
    for name in names:
        tool()(handlers[name])
    return names
