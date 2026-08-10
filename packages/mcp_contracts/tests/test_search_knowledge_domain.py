from __future__ import annotations

import pytest

from packages.mcp_contracts.src.domains.search_knowledge import (
    register_search_knowledge_tools,
    search_knowledge_tool_names,
)
from packages.mcp_contracts.src.tool_registry import default_tool_registry


def test_mcp101_registration_covers_exactly_the_catalog_domain() -> None:
    registry = default_tool_registry()
    registered: list[str] = []

    def tool():
        def decorate(handler):
            registered.append(handler.__name__)
            return handler
        return decorate

    handlers = {}
    for name in search_knowledge_tool_names(registry):
        def handler(_name=name):
            return _name
        handler.__name__ = name
        handlers[name] = handler

    assert register_search_knowledge_tools(tool, registry, handlers) == tuple(registered)
    assert set(registered) == {spec.name for spec in registry.discover(domain="search")}


def test_mcp101_registration_rejects_missing_compatibility_handler() -> None:
    registry = default_tool_registry()

    with pytest.raises(RuntimeError, match="MCP-101 handlers are missing: list_filter_facets"):
        register_search_knowledge_tools(lambda: lambda handler: handler, registry, {})
