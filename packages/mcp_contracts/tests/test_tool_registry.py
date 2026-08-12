from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from packages.mcp_contracts.src.tool_registry import (
    DuplicateToolNameError,
    ToolConfirmation,
    ToolDomain,
    ToolImpactScope,
    ToolRegistry,
    ToolReversibility,
    ToolRisk,
    ToolSpec,
    default_tool_registry,
    discover_tools,
    profile_tool_names,
    tool_policy_manifest,
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
    exposed = module._EXPOSED_TOOL_NAMES
    assert declared == exposed
    assert all(spec.handler is not None and spec.input_model is not None for spec in module._TOOL_REGISTRY.discover())


def test_discovery_filters_by_domain_risk_and_write_capability() -> None:
    registry = default_tool_registry()

    search_tools = registry.discover(domain=ToolDomain.SEARCH)
    high_risk_writes = discover_tools(risk=ToolRisk.HIGH, writable=True)

    assert search_tools
    assert all(spec.domain is ToolDomain.SEARCH for spec in search_tools)
    assert registry.get("search_questions").read_only is True
    assert registry.get("search_questions_compact").read_only is True
    assert registry.get("search_questions_curated").read_only is True
    assert registry.get("download_question_images").read_only is False
    assert registry.get("method_retrieval_learning_report").read_only is True
    assert registry.get("apply_composition_workbench_plan").risk is ToolRisk.MEDIUM
    assert registry.get("apply_composition_workbench_plan").impact_scope is ToolImpactScope.WORKBENCH_DRAFT
    assert registry.get("restore_saved_handout_version").reversibility is ToolReversibility.VERSIONED
    assert registry.get("publish_teaching_artifact").confirmation is ToolConfirmation.PLAN_TOKEN
    assert high_risk_writes
    assert all(spec.risk is ToolRisk.HIGH and not spec.read_only for spec in high_risk_writes)


def test_every_write_tool_has_explicit_impact_policy() -> None:
    manifest = tool_policy_manifest()
    assert len(manifest) == len(default_tool_registry().names())
    assert {item["name"] for item in manifest} == default_tool_registry().names()
    for item in manifest:
        if item["read_only"]:
            assert item["impact_scope"] == "none"
            assert item["confirmation"] == "none"
        else:
            assert item["impact_scope"] != "none"
            assert item["reversibility"] != "not_applicable"
            assert item["confirmation"] != "none"


def test_external_study_sheet_profile_cannot_access_composition_workbench() -> None:
    external_tools = profile_tool_names("external_study_sheet")
    assistant_tools = profile_tool_names("ai_assistant_workbench")

    assert "search_questions_compact" in external_tools
    assert "export_questions_to_typst" in external_tools
    assert "apply_composition_workbench_plan" not in external_tools
    assert "curate_questions_to_composition_workbench" not in external_tools
    assert "apply_composition_workbench_plan" in assistant_tools
    assert "curate_questions_to_composition_workbench" in assistant_tools


def test_external_catalog_maintenance_allows_metadata_without_workbench() -> None:
    tools = profile_tool_names("external_catalog_maintenance")

    assert "search_questions_compact" in tools
    assert "maintain_question_tags" in tools
    assert "maintain_question_knowledge_points" in tools
    assert "batch_update_question_metadata" in tools
    assert "apply_composition_workbench_plan" not in tools
    assert "curate_questions_to_composition_workbench" not in tools


def test_duplicate_tool_name_is_rejected_before_server_startup() -> None:
    declaration = ToolSpec("example", ToolDomain.SEARCH, ToolRisk.LOW, read_only=True)

    with pytest.raises(DuplicateToolNameError, match="Duplicate MCP tool name: example"):
        ToolRegistry((declaration, declaration))


def test_compact_search_omits_full_question_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_mcp_server()

    monkeypatch.setattr(
        module,
        "_legacy_search_questions",
        lambda **_: {
            "items": [{
                "question_id": "Q00000001", "title": "动量守恒示例题", "question_type": "单选题",
                "difficulty": 3, "knowledge_point": "动量守恒", "source": "2025 模拟卷",
                "year": 2025, "score": 0.99, "has_media": True, "image_count": 1,
                "answer": "A", "analysis": "很长的解析", "options": ["A", "B"], "figures": [{"id": "x"}],
            }],
            "total": 1, "limit": 12, "offset": 0, "search_mode": "hybrid",
        },
    )

    result = module._legacy_search_questions_compact(query="动量守恒")

    assert result["items"] == [{
        "question_id": "Q00000001", "title": "动量守恒示例题", "question_type": "单选题",
        "difficulty": 3, "knowledge_point": "动量守恒", "source": "2025 模拟卷",
        "year": 2025, "score": 0.99, "has_media": True, "image_count": 1,
    }]
    assert result["next_tool"] == "get_questions_by_ids"
