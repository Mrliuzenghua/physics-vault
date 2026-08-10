from __future__ import annotations

import pytest

from packages.mcp_contracts.src.domains.operations import (
    OperationsDomain,
    operations_tool_names,
    register_operations_tools,
)
from packages.mcp_contracts.src.tool_registry import ToolDomain, default_tool_registry, profile_tool_names


def test_mcp104_registration_covers_exactly_the_operations_domain() -> None:
    registry = default_tool_registry()
    registered: list[str] = []

    def tool():
        def decorate(handler):
            registered.append(handler.__name__)
            return handler
        return decorate

    handlers = {}
    for name in operations_tool_names(registry):
        def handler(_name=name):
            return {"name": _name}
        handler.__name__ = name
        handlers[name] = handler

    assert register_operations_tools(tool, registry, handlers) == tuple(registered)
    assert set(registered) == {spec.name for spec in registry.discover(domain=ToolDomain.OPERATIONS)}
    assert frozenset(registered) == profile_tool_names("operations")


def test_mcp104_registration_rejects_missing_compatibility_handler() -> None:
    registry = default_tool_registry()

    with pytest.raises(RuntimeError, match="MCP-104 handlers are missing: submit_import_job"):
        register_operations_tools(lambda: lambda handler: handler, registry, {})


def test_operations_domain_preserves_trace_and_audit_arguments() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    def handler(*args):
        calls.append(("retry_job", args))
        return {"ok": True, "audit_id": "audit-1"}

    result = OperationsDomain({"retry_job": handler}).retry_job(
        "task-1",
        True,
        "mcp",
        "session-1",
        "operator-1",
        "trace-1",
    )

    assert result == {"ok": True, "audit_id": "audit-1"}
    assert calls == [(
        "retry_job",
        ("task-1", True, "mcp", "session-1", "operator-1", "trace-1"),
    )]
