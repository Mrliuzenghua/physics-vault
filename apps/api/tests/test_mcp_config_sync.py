from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_checker():
    script = Path(__file__).resolve().parents[3] / "scripts" / "maintenance" / "check_mcp_config_sync.py"
    spec = importlib.util.spec_from_file_location("mcp_config_sync_for_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _server_map(root: str) -> dict:
    return {
        "physics_vault": {"env": {"PHYSICS_MCP_PROFILE": "all"}},
        "study_sheet_workflow": {"env": {"PHYSICS_STUDY_SHEET_ROOT": root}},
        "playwright": {"args": ["-y", "@playwright/mcp@0.0.78"]},
    }


def _write_inputs(module, tmp_path: Path, *, codex_root: str = "D:/teaching", disabled: bool = False) -> None:
    baseline = {
        "required_servers": ["physics_vault", "study_sheet_workflow", "playwright"],
        "physics_mcp_profile": "all",
        "study_sheet_root": None,
        "playwright_package": "@playwright/mcp@0.0.78",
        "playwright_required_args": [],
    }
    project_servers = _server_map("D:/teaching")
    claude_servers = _server_map("D:/teaching")
    codex_filter = 'disabled_tools = ["unsafe"]\n' if disabled else ""
    codex = f'''[mcp_servers.physics_vault]\n{codex_filter}[mcp_servers.physics_vault.env]\nPHYSICS_MCP_PROFILE = "all"\n\n[mcp_servers.study_sheet_workflow.env]\nPHYSICS_STUDY_SHEET_ROOT = "{codex_root}"\n\n[mcp_servers.playwright]\nargs = ["-y", "@playwright/mcp@0.0.78"]\n'''

    module.BASELINE_PATH = tmp_path / "baseline.json"
    module.PROJECT_CONFIG_PATH = tmp_path / "project.json"
    module.CODEX_CONFIG_PATH = tmp_path / "codex.toml"
    module.CLAUDE_CONFIG_PATH = tmp_path / "claude.json"
    module.BASELINE_PATH.write_text(json.dumps(baseline), encoding="utf-8")
    module.PROJECT_CONFIG_PATH.write_text(json.dumps({"mcpServers": project_servers}), encoding="utf-8")
    module.CODEX_CONFIG_PATH.write_text(codex, encoding="utf-8")
    module.CLAUDE_CONFIG_PATH.write_text(json.dumps({"mcpServers": claude_servers}), encoding="utf-8")


def test_mcp_config_sync_uses_a_configured_client_as_portable_path_baseline(tmp_path: Path) -> None:
    module = _load_checker()
    _write_inputs(module, tmp_path)

    result = module.check()

    assert result["ok"] is True
    assert result["study_sheet_root_source"] == "configured_client"
    assert result["issues"] == []


def test_mcp_config_sync_reports_filters_and_path_drift(tmp_path: Path) -> None:
    module = _load_checker()
    _write_inputs(module, tmp_path, codex_root="D:/other", disabled=True)

    result = module.check()
    issues = {(item["client"], item["issue"]) for item in result["issues"]}

    assert result["ok"] is False
    assert ("codex", "unexpected_disabled_tools") in issues
    assert ("codex", "study_root_mismatch") in issues


def test_mcp_config_sync_reports_missing_client_config(tmp_path: Path) -> None:
    module = _load_checker()
    _write_inputs(module, tmp_path)
    module.CLAUDE_CONFIG_PATH.unlink()

    result = module.check()

    assert result["ok"] is False
    assert {"client": "claude", "server": "*", "issue": "config_missing"} in result["issues"]
