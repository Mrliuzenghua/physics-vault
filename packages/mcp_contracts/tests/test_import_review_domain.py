from __future__ import annotations

import pytest

from packages.mcp_contracts.src.domains.import_review import (
    ImportReviewDomain,
    import_review_tool_names,
    register_import_review_tools,
)
from packages.mcp_contracts.src.tool_registry import default_tool_registry


def test_mcp102_registration_covers_exactly_the_import_review_domain() -> None:
    registry = default_tool_registry()
    registered: list[str] = []

    def tool():
        def decorate(handler):
            registered.append(handler.__name__)
            return handler
        return decorate

    handlers = {}
    for name in import_review_tool_names(registry):
        def handler(_name=name):
            return {"name": _name}
        handler.__name__ = name
        handlers[name] = handler

    assert register_import_review_tools(tool, registry, handlers) == tuple(registered)
    assert set(registered) == {spec.name for spec in registry.discover(domain="import_review")}


def test_mcp102_registration_rejects_missing_compatibility_handler() -> None:
    registry = default_tool_registry()

    with pytest.raises(RuntimeError, match="MCP-102 handlers are missing: list_review_queue"):
        register_import_review_tools(lambda: lambda handler: handler, registry, {})


def test_import_review_domain_preserves_public_arguments_and_result() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    def handler(*args):
        calls.append(("validate_review_task", args))
        return {"ok": True, "items": []}

    result = ImportReviewDomain({"validate_review_task": handler}).validate_review_task(
        "task-1",
        ["question-1"],
        require_knowledge=False,
        require_source=False,
        risks_only=True,
    )

    assert result == {"ok": True, "items": []}
    assert calls == [("validate_review_task", ("task-1", ["question-1"], False, False, True))]
