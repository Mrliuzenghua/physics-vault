"""Reusable health-report builders for the MCP runtime."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def study_sheet_template_health(raw_root: str | Path | None) -> dict[str, Any]:
    """Validate the configured study-sheet template registry and checksums."""
    root_value = str(raw_root or "").strip()
    if not root_value:
        return {"status": "not_configured", "passed": None, "checks": []}
    root = Path(root_value).expanduser().resolve()
    registry_path = root / "01-模板" / "templates.json"
    if not registry_path.is_file():
        return {"status": "registry_missing", "passed": False, "registry_path": str(registry_path), "checks": []}
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "registry_invalid",
            "passed": False,
            "registry_path": str(registry_path),
            "error": str(exc),
            "checks": [],
        }
    if not isinstance(registry, dict) or not isinstance(registry.get("templates", []), list):
        return {
            "status": "registry_invalid",
            "passed": False,
            "registry_path": str(registry_path),
            "error": "templates.json must contain a templates array",
            "checks": [],
        }
    checks: list[dict[str, Any]] = []
    for item in registry.get("templates", []):
        if not isinstance(item, dict):
            checks.append({"id": None, "file": None, "passed": False})
            continue
        file_path = (registry_path.parent / str(item.get("template_file") or "")).resolve()
        inside = file_path.parent == registry_path.parent
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest() if inside and file_path.is_file() else None
        checks.append(
            {
                "id": item.get("id"),
                "file": item.get("template_file"),
                "passed": bool(actual and actual == item.get("template_sha256")),
            }
        )
    passed = bool(checks) and all(item["passed"] for item in checks)
    return {
        "status": "ok" if passed else "attention",
        "passed": passed,
        "registry_path": str(registry_path),
        "checks": checks,
    }


def build_mcp_system_health(
    *,
    profile: str,
    database: Mapping[str, Any],
    templates: Mapping[str, Any],
    embeddings: Mapping[str, Any],
    policies: Sequence[Mapping[str, Any]],
    operations: Mapping[str, Any] | None = None,
    include_details: bool = False,
) -> dict[str, Any]:
    """Combine independently collected health signals into the public response."""

    def counts(field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in policies:
            key = str(item[field])
            result[key] = result.get(key, 0) + 1
        return result

    issues = list(database.get("issues") or [])
    if templates.get("passed") is False:
        issues.append({"code": "study_sheet_template_integrity", "severity": "high"})
    if embeddings.get("status") != "ok":
        issues.append(
            {
                "code": "semantic_embedding_coverage",
                "severity": "medium",
                "coverage": embeddings.get("coverage"),
            }
        )
    operation_health = dict(operations or {})
    issues.extend(list(operation_health.get("issues") or []))
    high_risk_writes = [
        item for item in policies
        if item.get("risk") == "high" and not bool(item.get("read_only"))
    ]
    unprotected_high_risk = [
        str(item.get("name"))
        for item in high_risk_writes
        if str(item.get("confirmation") or "none") in {"none", "direct"}
    ]
    if unprotected_high_risk:
        issues.append({
            "code": "high_risk_confirmation_gap",
            "severity": "high",
            "count": len(unprotected_high_risk),
            "tools": unprotected_high_risk,
        })
    response: dict[str, Any] = {
        "ok": True,
        "status": "attention" if issues else "ok",
        "server": {"name": "physics_vault", "version": "0.2.0", "profile": profile},
        "tool_surface": {
            "total": len(policies),
            "read_only": sum(1 for item in policies if item["read_only"]),
            "writable": sum(1 for item in policies if not item["read_only"]),
            "by_domain": counts("domain"),
            "by_risk": counts("risk"),
            "by_impact_scope": counts("impact_scope"),
        },
        "database": {
            "canonical_path": database.get("canonical_database_path"),
            "review_path": database.get("review_database_path"),
            "counts": database.get("counts"),
            "review_workspace": database.get("review_workspace"),
        },
        "embeddings": dict(embeddings),
        "study_sheet_templates": dict(templates),
        "operations": operation_health,
        "safety_controls": {
            "high_risk_write_count": len(high_risk_writes),
            "confirmation_protected_count": len(high_risk_writes) - len(unprotected_high_risk),
            "confirmation_coverage": (
                round((len(high_risk_writes) - len(unprotected_high_risk)) / len(high_risk_writes), 4)
                if high_risk_writes else 1.0
            ),
            "unprotected_tools": unprotected_high_risk,
        },
        "issues": issues,
        "next_tools": ["get_workflow_guide", "database_boundary_report", "database_health_report"],
    }
    if include_details:
        response["tool_policies"] = list(policies)
        response["database_details"] = dict(database)
    return response
