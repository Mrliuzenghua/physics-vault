"""Shared, transport-safe plan contract for high-risk write operations."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field


class OperationTarget(BaseModel):
    """A single entity or bounded scope affected by a planned operation."""

    id: str
    type: str
    label: str | None = None


class OperationPlan(BaseModel):
    """The stable preview contract shared by MCP and HTTP write workflows."""

    operation_id: str
    action: str
    targets: list[OperationTarget] = Field(default_factory=list)
    expected_version: str | None = None
    summary: str
    warnings: list[str] = Field(default_factory=list)
    expires_at: datetime
    reversible: bool
    status: str = "planned"


def snapshot_version(value: Any) -> str:
    """Create a compact version token for a previewed input snapshot."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_operation_plan(
    *,
    action: str,
    targets: list[OperationTarget | dict[str, Any]],
    summary: str,
    warnings: list[str] | None = None,
    expected_version: str | None = None,
    version_snapshot: Any = None,
    reversible: bool,
    expires_in_minutes: int = 15,
) -> OperationPlan:
    """Build an expiring preview that SAFE-202 can persist and confirm."""
    normalized_action = str(action or "operation").strip() or "operation"
    normalized_targets = [
        target if isinstance(target, OperationTarget) else OperationTarget.model_validate(target)
        for target in targets
    ]
    lifetime = min(max(int(expires_in_minutes or 15), 1), 60)
    return OperationPlan(
        operation_id=f"OP-{uuid.uuid4().hex}",
        action=normalized_action,
        targets=normalized_targets,
        expected_version=expected_version or snapshot_version(version_snapshot or normalized_targets),
        summary=str(summary).strip(),
        warnings=[str(item).strip() for item in (warnings or []) if str(item).strip()],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=lifetime),
        reversible=bool(reversible),
    )


__all__ = ["OperationPlan", "OperationTarget", "build_operation_plan", "snapshot_version"]
