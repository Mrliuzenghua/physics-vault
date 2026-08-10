from __future__ import annotations

import pytest

from packages.mcp_contracts.src.domains.authoring import (
    AuthoringDomain,
    authoring_tool_names,
    register_authoring_tools,
)
from packages.mcp_contracts.src.tool_registry import ToolDomain, default_tool_registry, profile_tool_names


def test_mcp103_registration_covers_exactly_the_authoring_domain() -> None:
    registry = default_tool_registry()
    registered: list[str] = []

    def tool():
        def decorate(handler):
            registered.append(handler.__name__)
            return handler
        return decorate

    handlers = {}
    for name in authoring_tool_names(registry):
        def handler(_name=name):
            return {"name": _name}
        handler.__name__ = name
        handlers[name] = handler

    assert register_authoring_tools(tool, registry, handlers) == tuple(registered)
    assert set(registered) == {spec.name for spec in registry.discover(domain=ToolDomain.AUTHORING)}
    assert frozenset(registered) == profile_tool_names("authoring")


def test_mcp103_registration_rejects_missing_compatibility_handler() -> None:
    registry = default_tool_registry()

    with pytest.raises(RuntimeError, match="MCP-103 handlers are missing: list_teaching_projects"):
        register_authoring_tools(lambda: lambda handler: handler, registry, {})


def test_authoring_domain_preserves_arguments_and_result() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    def handler(*args):
        calls.append(("apply_composition_workbench_plan", args))
        return {"ok": True, "document_kind": "workbench_draft"}

    result = AuthoringDomain({"apply_composition_workbench_plan": handler}).apply_composition_workbench_plan(
        [{"op": "add_question", "question_id": "question-1"}],
        "draft-1",
        ["question-1"],
        "patch",
        True,
    )

    assert result == {"ok": True, "document_kind": "workbench_draft"}
    assert calls == [(
        "apply_composition_workbench_plan",
        ([{"op": "add_question", "question_id": "question-1"}], "draft-1", ["question-1"], "patch", True),
    )]
