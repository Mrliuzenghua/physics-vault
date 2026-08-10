"""Shared, transport-safe plan contract for high-risk write operations."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OperationTarget(BaseModel):
    """A single entity or bounded scope affected by a planned operation."""

    id: str
    type: str
    label: str | None = None


class BatchMetadataUpdate(BaseModel):
    """One precomputed, bounded question-metadata write."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(..., min_length=1)
    knowledge_point: str | None = None
    tags: list[str] | None = None
    source: str | None = None

    @model_validator(mode="after")
    def has_update(self) -> "BatchMetadataUpdate":
        if self.knowledge_point is None and self.tags is None and self.source is None:
            raise ValueError("metadata update must contain at least one field")
        return self


class BatchMetadataSkip(BaseModel):
    """A previewed target that deliberately has no write to perform."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(..., min_length=1)
    message: str = "已有内容，已跳过"


class BatchMetadataExecutionPayload(BaseModel):
    """The only execution payload currently permitted in an operation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["batch_metadata"] = "batch_metadata"
    question_ids: list[str] = Field(..., min_length=1, max_length=500)
    updates: list[BatchMetadataUpdate] = Field(default_factory=list)
    skips: list[BatchMetadataSkip] = Field(default_factory=list)

    @field_validator("question_ids")
    @classmethod
    def unique_question_ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(question_id).strip() for question_id in value]
        if any(not question_id for question_id in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("question_ids must be non-empty and unique")
        return cleaned

    @model_validator(mode="after")
    def covers_every_target_once(self) -> "BatchMetadataExecutionPayload":
        target_ids = set(self.question_ids)
        covered = [item.question_id for item in self.updates] + [item.question_id for item in self.skips]
        if set(covered) != target_ids or len(covered) != len(target_ids):
            raise ValueError("execution payload must cover every question exactly once")
        return self


class OperationPlan(BaseModel):
    """The stable preview contract shared by MCP and HTTP write workflows."""

    operation_id: str
    action: str
    targets: list[OperationTarget] = Field(default_factory=list)
    expected_version: str | None = None
    version_snapshot: dict[str, Any] = Field(default_factory=dict)
    execution_payload: BatchMetadataExecutionPayload | None = None
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
    execution_payload: BatchMetadataExecutionPayload | None = None,
    reversible: bool,
    expires_in_minutes: int = 15,
) -> OperationPlan:
    """Build an expiring preview that SAFE-202 can persist and confirm."""
    normalized_action = str(action or "operation").strip() or "operation"
    normalized_targets = [
        target if isinstance(target, OperationTarget) else OperationTarget.model_validate(target)
        for target in targets
    ]
    normalized_snapshot = (
        dict(version_snapshot)
        if isinstance(version_snapshot, dict)
        else ({"snapshot": version_snapshot} if version_snapshot is not None else {})
    )
    lifetime = min(max(int(expires_in_minutes or 15), 1), 60)
    return OperationPlan(
        operation_id=f"OP-{uuid.uuid4().hex}",
        action=normalized_action,
        targets=normalized_targets,
        expected_version=expected_version or snapshot_version(normalized_snapshot or normalized_targets),
        version_snapshot=normalized_snapshot,
        execution_payload=execution_payload,
        summary=str(summary).strip(),
        warnings=[str(item).strip() for item in (warnings or []) if str(item).strip()],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=lifetime),
        reversible=bool(reversible),
    )


__all__ = [
    "BatchMetadataExecutionPayload",
    "BatchMetadataSkip",
    "BatchMetadataUpdate",
    "OperationPlan",
    "OperationTarget",
    "build_operation_plan",
    "snapshot_version",
]
