from __future__ import annotations

from scripts.maintenance import run_mcp_health_check as health_check


def test_health_check_fails_only_critical_runtime_issues(monkeypatch) -> None:
    monkeypatch.setattr(health_check, "check_config", lambda: {"ok": True})
    monkeypatch.setattr(
        health_check,
        "evaluate_retrieval",
        lambda: {"metrics": {"missing_expected_years": [], "empty_filter_case_count": 0, "filter_leak_count": 0, "latency_p95_ms": 1}},
    )
    monkeypatch.setattr(health_check, "check_retrieval", lambda _report: [])
    import scripts.physics_vault_mcp_server as mcp_server

    monkeypatch.setattr(
        mcp_server,
        "mcp_system_health",
        lambda include_details=False: {
            "tool_surface": {"total": 104},
            "operations": {"active_task_count": 0},
            "study_sheet_templates": {"passed": True},
            "embeddings": {"coverage": 1.0},
            "issues": [{"code": "metadata_backlog", "severity": "medium"}],
        },
    )

    report = health_check.run()

    assert report["ok"] is True
    assert report["status"] == "attention"
