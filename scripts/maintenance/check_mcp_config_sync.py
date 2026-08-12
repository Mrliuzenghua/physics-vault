"""Read-only drift check for the project, Codex, and Claude MCP clients."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOCAL_BASELINE_PATH = ROOT / "config" / "mcp_client_baseline.json"
EXAMPLE_BASELINE_PATH = ROOT / "config" / "examples" / "mcp_client_baseline.example.json"
BASELINE_PATH = Path(os.getenv("PHYSICS_MCP_BASELINE_PATH") or (
    LOCAL_BASELINE_PATH if LOCAL_BASELINE_PATH.is_file() else EXAMPLE_BASELINE_PATH
)).expanduser()
PROJECT_CONFIG_PATH = ROOT / ".mcp.json"
CODEX_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
CLAUDE_CONFIG_PATH = Path.home() / ".claude.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _normalized_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").rstrip("/").casefold()


def _contains_arg(server: dict[str, Any], expected: str) -> bool:
    return expected in [str(value) for value in server.get("args", [])]


def _arg_value(server: dict[str, Any], flag: str) -> str | None:
    args = [str(value) for value in server.get("args", [])]
    try:
        index = args.index(flag)
    except ValueError:
        return None
    return args[index + 1] if index + 1 < len(args) else None


def _client_servers(
    path: Path,
    *,
    client: str,
    container_key: str,
    parser: Any,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    if not path.is_file():
        issues.append({"client": client, "server": "*", "issue": "config_missing"})
        return {}
    try:
        payload = parser(path)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        issues.append({"client": client, "server": "*", "issue": f"config_invalid={exc}"})
        return {}
    servers = payload.get(container_key, {}) if isinstance(payload, dict) else {}
    if not isinstance(servers, dict):
        issues.append({"client": client, "server": "*", "issue": "server_map_invalid"})
        return {}
    return servers


def check() -> dict[str, Any]:
    baseline = _json(BASELINE_PATH)
    issues: list[dict[str, str]] = []
    project = _client_servers(
        PROJECT_CONFIG_PATH, client="project", container_key="mcpServers", parser=_json, issues=issues
    )
    codex = _client_servers(
        CODEX_CONFIG_PATH, client="codex", container_key="mcp_servers", parser=_toml, issues=issues
    )
    claude = _client_servers(
        CLAUDE_CONFIG_PATH, client="claude", container_key="mcpServers", parser=_json, issues=issues
    )
    clients = {"project": project, "codex": codex, "claude": claude}
    expected_servers = set(baseline["required_servers"])
    expected_study_root = _normalized_path(baseline.get("study_sheet_root"))
    if not expected_study_root:
        expected_study_root = next((
            _normalized_path(servers.get("study_sheet_workflow", {}).get("env", {}).get("PHYSICS_STUDY_SHEET_ROOT"))
            for servers in clients.values()
            if _normalized_path(servers.get("study_sheet_workflow", {}).get("env", {}).get("PHYSICS_STUDY_SHEET_ROOT"))
        ), "")

    for client_name, servers in clients.items():
        missing = sorted(expected_servers - set(servers))
        for server_name in missing:
            issues.append({"client": client_name, "server": server_name, "issue": "missing_server"})

        physics = servers.get("physics_vault", {})
        if physics:
            profile = physics.get("env", {}).get("PHYSICS_MCP_PROFILE")
            if profile != baseline["physics_mcp_profile"]:
                issues.append({"client": client_name, "server": "physics_vault", "issue": f"profile={profile!r}"})
            for filter_name in ("disabled_tools", "enabled_tools"):
                if physics.get(filter_name):
                    issues.append({"client": client_name, "server": "physics_vault", "issue": f"unexpected_{filter_name}"})

        study = servers.get("study_sheet_workflow", {})
        if study:
            actual_root = _normalized_path(study.get("env", {}).get("PHYSICS_STUDY_SHEET_ROOT"))
            if not actual_root:
                issues.append({"client": client_name, "server": "study_sheet_workflow", "issue": "study_root_missing"})
            elif expected_study_root and actual_root != expected_study_root:
                issues.append({"client": client_name, "server": "study_sheet_workflow", "issue": "study_root_mismatch"})

        playwright = servers.get("playwright", {})
        if playwright and not _contains_arg(playwright, baseline["playwright_package"]):
            issues.append({"client": client_name, "server": "playwright", "issue": "playwright_version_drift"})
        for expected_arg in baseline.get("playwright_required_args", []):
            if playwright and not _contains_arg(playwright, str(expected_arg)):
                issues.append({"client": client_name, "server": "playwright", "issue": f"missing_arg={expected_arg}"})
        if playwright:
            expected_output_dir = _normalized_path(baseline.get("playwright_output_dir"))
            actual_output_dir = _normalized_path(_arg_value(playwright, "--output-dir"))
            if expected_output_dir and actual_output_dir != expected_output_dir:
                issues.append({"client": client_name, "server": "playwright", "issue": "output_dir_mismatch"})
            expected_output_size = str(baseline.get("playwright_output_max_size") or "")
            if expected_output_size and _arg_value(playwright, "--output-max-size") != expected_output_size:
                issues.append({"client": client_name, "server": "playwright", "issue": "output_max_size_mismatch"})

    return {
        "ok": not issues,
        "baseline": str(BASELINE_PATH),
        "clients_checked": list(clients),
        "required_servers": sorted(expected_servers),
        "study_sheet_root_source": "baseline" if baseline.get("study_sheet_root") else "configured_client",
        "issues": issues,
    }


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
