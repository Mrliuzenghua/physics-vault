from __future__ import annotations

import hashlib
import json

from packages.mcp_contracts.src.runtime import (
    build_mcp_system_health,
    build_workflow_guide,
    study_sheet_template_health,
)


def test_workflow_guide_matches_intent_and_filters_unexposed_tools() -> None:
    result = build_workflow_guide(
        "我要组卷并调整题目顺序",
        profile="authoring",
        exposed_tools={"create_composition_workbench", "preview_composition_workbench"},
    )

    assert result["matched_count"] == 1
    workflow = result["workflows"][0]
    assert workflow["id"] == "composition"
    assert workflow["start_tool"] == "create_composition_workbench"
    assert workflow["tools"] == ["create_composition_workbench", "preview_composition_workbench"]
    assert "export_composition_workbench" in workflow["unavailable_tools"]


def test_workflow_guide_returns_all_workflows_for_unknown_intent() -> None:
    result = build_workflow_guide("完全未知的操作", profile="all", exposed_tools=set())

    assert result["matched_count"] == 8
    assert all(workflow["start_tool"] is None for workflow in result["workflows"])


def test_study_sheet_template_health_verifies_registry_checksum(tmp_path) -> None:
    template_dir = tmp_path / "01-模板"
    template_dir.mkdir()
    template = template_dir / "sheet.typ"
    template.write_bytes(b"template-content")
    registry = {
        "templates": [
            {
                "id": "default",
                "template_file": template.name,
                "template_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
            }
        ]
    }
    (template_dir / "templates.json").write_text(json.dumps(registry), encoding="utf-8")

    healthy = study_sheet_template_health(tmp_path)
    assert healthy["status"] == "ok"
    assert healthy["passed"] is True

    template.write_bytes(b"tampered")
    unhealthy = study_sheet_template_health(tmp_path)
    assert unhealthy["status"] == "attention"
    assert unhealthy["passed"] is False


def test_system_health_aggregates_policy_counts_and_details() -> None:
    database = {
        "canonical_database_path": "formal.db",
        "review_database_path": "review.db",
        "counts": {"questions": 12},
        "review_workspace": {"tasks": 2},
        "issues": [],
    }
    policies = [
        {"name": "read", "read_only": True, "domain": "search", "risk": "low", "impact_scope": "none"},
        {"name": "write", "read_only": False, "domain": "review", "risk": "high", "impact_scope": "review"},
    ]

    result = build_mcp_system_health(
        profile="all",
        database=database,
        templates={"status": "not_configured", "passed": None, "checks": []},
        embeddings={"status": "attention", "coverage": 0.5},
        policies=policies,
        include_details=True,
    )

    assert result["status"] == "attention"
    assert result["tool_surface"] == {
        "total": 2,
        "read_only": 1,
        "writable": 1,
        "by_domain": {"search": 1, "review": 1},
        "by_risk": {"low": 1, "high": 1},
        "by_impact_scope": {"none": 1, "review": 1},
    }
    assert result["issues"] == [
        {"code": "semantic_embedding_coverage", "severity": "medium", "coverage": 0.5}
    ]
    assert result["tool_policies"] == policies
    assert result["database_details"] == database
