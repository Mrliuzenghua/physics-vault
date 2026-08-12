"""Run the MCP configuration, runtime, template, and retrieval health gates."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.maintenance.check_mcp_config_sync import BASELINE_PATH, check as check_config  # noqa: E402
from scripts.maintenance.evaluate_filter_retrieval import (  # noqa: E402
    check as check_retrieval,
    evaluate as evaluate_retrieval,
)


def _configure_template_root() -> None:
    if os.getenv("PHYSICS_STUDY_SHEET_ROOT"):
        return
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    configured = str(baseline.get("study_sheet_root") or "").strip()
    if configured:
        os.environ["PHYSICS_STUDY_SHEET_ROOT"] = configured


def run(*, include_retrieval: bool = True) -> dict[str, Any]:
    _configure_template_root()
    import scripts.physics_vault_mcp_server as mcp_server

    config = check_config()
    runtime = mcp_server.mcp_system_health(include_details=False)
    retrieval = evaluate_retrieval() if include_retrieval else None
    retrieval_failures = check_retrieval(retrieval) if retrieval is not None else []
    failures: list[str] = []
    if not config.get("ok"):
        failures.append("mcp_client_config_drift")
    failures.extend(f"retrieval:{item}" for item in retrieval_failures)
    failures.extend(
        f"runtime:{issue.get('code')}"
        for issue in runtime.get("issues", [])
        if issue.get("severity") == "high"
    )
    warning_count = sum(
        issue.get("severity") in {"medium", "low"} for issue in runtime.get("issues", [])
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": not failures,
        "status": "failed" if failures else ("attention" if warning_count else "ok"),
        "failures": failures,
        "summary": {
            "config_synced": bool(config.get("ok")),
            "tool_count": runtime.get("tool_surface", {}).get("total"),
            "active_task_count": runtime.get("operations", {}).get("active_task_count"),
            "template_integrity": runtime.get("study_sheet_templates", {}).get("passed"),
            "embedding_coverage": runtime.get("embeddings", {}).get("coverage"),
            "high_risk_confirmation_coverage": runtime.get("safety_controls", {}).get("confirmation_coverage"),
            "runtime_issue_count": len(runtime.get("issues", [])),
            "retrieval_metrics": retrieval.get("metrics") if retrieval else None,
        },
        "config": config,
        "runtime": runtime,
        "retrieval": retrieval,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit nonzero when a critical gate fails")
    parser.add_argument("--skip-retrieval", action="store_true", help="skip the slower retrieval benchmark")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "health" / "mcp-health-latest.json",
    )
    args = parser.parse_args()
    report = run(include_retrieval=not args.skip_retrieval)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["summary"]}, ensure_ascii=False, indent=2))
    print(f"report: {args.output}")
    return 1 if args.check and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
