"""Audit-context construction shared by MCP write operations."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from physics_vault_api.services.task_center import TaskActionContext


def build_task_action_context(
    source: str,
    session_id: str | None,
    operator: str,
    *,
    confirmed: bool = False,
    trace_id: str | None = None,
    operation_id: str | None = None,
) -> TaskActionContext:
    """Create the application audit context with bounded, normalized fields."""
    # Imported lazily so this common contract package does not require the API
    # application merely to be imported or unit tested.
    from physics_vault_api.services.task_center import TaskActionContext
    from physics_vault_api.observability import resolve_trace_id

    normalized_operation_id = str(operation_id or "").strip()
    if normalized_operation_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", normalized_operation_id):
        raise ValueError("operation_id must contain only letters, digits, underscores, or hyphens (max 80)")
    return TaskActionContext(
        source=(str(source or "physics_vault_mcp").strip() or "physics_vault_mcp")[:120],
        session_id=(str(session_id).strip()[:160] if session_id else None),
        operator=(str(operator or "MCP user").strip() or "MCP user")[:120],
        confirmed=confirmed,
        trace_id=resolve_trace_id(trace_id),
        operation_id=normalized_operation_id or None,
    )
