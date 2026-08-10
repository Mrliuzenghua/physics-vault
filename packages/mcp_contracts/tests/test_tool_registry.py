from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from packages.mcp_contracts.src.tool_registry import (
    DuplicateToolNameError,
    ToolDomain,
    ToolRegistry,
    ToolRisk,
    ToolSpec,
    default_tool_registry,
    discover_tools,
)


def _load_mcp_server():
    server_path = Path(__file__).resolve().parents[3] / "scripts" / "physics_vault_mcp_server.py"
    spec = importlib.util.spec_from_file_location("physics_vault_mcp_server_registry_test", server_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalogue_has_bound_handler_and_matches_exposed_mcp_tools() -> None:
    module = _load_mcp_server()
    module._validate_tool_registry()

    declared = module._TOOL_REGISTRY.names()
    exposed = {tool.name for tool in module.server._tool_manager.list_tools()}
    assert declared == exposed
    assert all(spec.handler is not None and spec.input_model is not None for spec in module._TOOL_REGISTRY.discover())


def test_discovery_filters_by_domain_risk_and_write_capability() -> None:
    registry = default_tool_registry()

    search_tools = registry.discover(domain=ToolDomain.SEARCH)
    high_risk_writes = discover_tools(risk=ToolRisk.HIGH, writable=True)

    assert search_tools
    assert all(spec.domain is ToolDomain.SEARCH for spec in search_tools)
    assert registry.get("search_questions").read_only is True
    assert registry.get("download_question_images").read_only is False
    assert high_risk_writes
    assert all(spec.risk is ToolRisk.HIGH and not spec.read_only for spec in high_risk_writes)


def test_duplicate_tool_name_is_rejected_before_server_startup() -> None:
    declaration = ToolSpec("example", ToolDomain.SEARCH, ToolRisk.LOW, read_only=True)

    with pytest.raises(DuplicateToolNameError, match="Duplicate MCP tool name: example"):
        ToolRegistry((declaration, declaration))
