from __future__ import annotations

from datetime import datetime, timezone

from packages.mcp_contracts.src.operation_plan import build_operation_plan


def test_operation_plan_has_safe_execution_defaults() -> None:
    plan = build_operation_plan(
        action="questions.batch-update",
        targets=[{"type": "question", "id": "q-1"}],
        summary="update one question",
        version_snapshot={"q-1": 1},
        reversible=True,
    )

    assert plan.status == "planned"
    assert plan.expected_version
    assert plan.expires_at > datetime.now(timezone.utc)
