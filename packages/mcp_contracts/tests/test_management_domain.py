from __future__ import annotations

import pytest

from packages.mcp_contracts.src.domains.management import (
    ManagementDomain,
    management_tool_names,
    register_management_tools,
)
from packages.mcp_contracts.src.tool_registry import ToolDomain, default_tool_registry, profile_tool_names


def test_mcp105_registration_covers_exactly_the_management_domain() -> None:
    registry = default_tool_registry()
    registered: list[str] = []

    def tool():
        def decorate(handler):
            registered.append(handler.__name__)
            return handler
        return decorate

    handlers = {}
    for name in management_tool_names(registry):
        def handler(_name=name):
            return {"name": _name}
        handler.__name__ = name
        handlers[name] = handler

    assert register_management_tools(tool, registry, handlers) == tuple(registered)
    assert set(registered) == {spec.name for spec in registry.discover(domain=ToolDomain.MANAGEMENT)}
    assert frozenset(registered) == profile_tool_names("catalog_maintenance")


def test_mcp105_registration_rejects_missing_compatibility_handler() -> None:
    registry = default_tool_registry()

    with pytest.raises(RuntimeError, match="MCP-105 handlers are missing: create_knowledge_points"):
        register_management_tools(lambda: lambda handler: handler, registry, {})


def test_management_domain_preserves_preview_reason_and_audit_arguments() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    def handler(*args):
        calls.append(("merge_canonical_duplicate_questions", args))
        return {"ok": True, "dry_run": True, "audit_id": "audit-1"}

    result = ManagementDomain({"merge_canonical_duplicate_questions": handler}).merge_canonical_duplicate_questions(
        "question-primary",
        ["question-duplicate"],
        True,
        "merge duplicate",
    )

    assert result == {"ok": True, "dry_run": True, "audit_id": "audit-1"}
    assert calls == [(
        "merge_canonical_duplicate_questions",
        ("question-primary", ["question-duplicate"], True, "merge duplicate"),
    )]
