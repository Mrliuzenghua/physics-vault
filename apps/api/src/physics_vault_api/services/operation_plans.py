"""Application adapters for the shared high-risk operation-plan contract."""

from __future__ import annotations

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mcp_contracts.src.operation_plan import (
    BatchMetadataExecutionPayload,
    OperationPlan,
    build_operation_plan,
    snapshot_version,
)

from ..repositories.operation_plans import OperationPlanRepository, StoredOperationPlan


class OperationPlanError(RuntimeError):
    pass


class OperationPlanVersionConflict(OperationPlanError):
    pass


@dataclass(frozen=True, slots=True)
class OperationExecutionResult:
    operation_id: str
    status: str
    result: Any | None = None
    error: str | None = None
    idempotent: bool = False


class OperationPlanService:
    """Confirmation kernel: persist preview, validate version, claim once, then finalize."""

    def __init__(self, repository: OperationPlanRepository, *, now: Callable[[], datetime] | None = None) -> None:
        self._repository = repository
        self._now = now or (lambda: datetime.now(timezone.utc))

    def save_preview(self, plan: OperationPlan) -> StoredOperationPlan:
        return self._repository.save(plan)

    def execute(
        self,
        operation_id: str,
        *,
        version_reader: Callable[[OperationPlan], str] | None = None,
        executor: Callable[[OperationPlan], Any],
    ) -> OperationExecutionResult:
        existing = self._require(operation_id)
        if existing.status == "completed":
            return _result(existing, idempotent=True)
        if existing.status in {"failed", "expired", "executing"}:
            return _result(existing)
        if existing.plan.expires_at <= self._now():
            claim = self._repository.claim(operation_id, now=self._now())
            return _result(claim[0] if claim is not None else existing)
        if version_reader is not None:
            actual_version = version_reader(existing.plan)
            if actual_version != existing.plan.expected_version:
                raise OperationPlanVersionConflict(
                    f"expected version {existing.plan.expected_version}, got {actual_version}"
                )
        claim = self._repository.claim(operation_id, now=self._now())
        if claim is None:
            raise OperationPlanError("operation plan not found")
        claimed, acquired = claim
        if not acquired:
            return _result(claimed, idempotent=claimed.status == "completed")
        try:
            return _result(self._repository.complete(operation_id, executor(claimed.plan), now=self._now()))
        except OperationPlanVersionConflict as exc:
            self._repository.fail(operation_id, str(exc), now=self._now())
            raise
        except Exception as exc:
            return _result(self._repository.fail(operation_id, str(exc), now=self._now()))

    def _require(self, operation_id: str) -> StoredOperationPlan:
        stored = self._repository.get(operation_id)
        if stored is None:
            raise OperationPlanError("operation plan not found")
        return stored


def _result(stored: StoredOperationPlan, *, idempotent: bool = False) -> OperationExecutionResult:
    return OperationExecutionResult(
        operation_id=stored.plan.operation_id,
        status=stored.status,
        result=stored.result,
        error=stored.error,
        idempotent=idempotent,
    )


def build_asset_cleanup_plan(
    *,
    action: str,
    scope: str,
    candidate_count: int,
    reclaimable_bytes: int,
    batch_id: str | None = None,
    protected_count: int = 0,
) -> OperationPlan:
    """Describe an asset cleanup preview using the MCP/API shared shape."""
    warning = (
        f"{protected_count} 个受引用或活动任务保护的素材不会被清理。"
        if protected_count
        else "清理会删除候选素材；请在计划过期前确认范围。"
    )
    plan = build_operation_plan(
        action=action,
        targets=[{"type": "asset_cleanup_scope", "id": batch_id or scope, "label": scope}],
        summary=f"计划清理 {candidate_count} 个素材，预计释放 {reclaimable_bytes} 字节。",
        warnings=[warning],
        version_snapshot={
            "scope": scope,
            "batch_id": batch_id,
            "candidate_count": candidate_count,
            "reclaimable_bytes": reclaimable_bytes,
            "protected_count": protected_count,
        },
        reversible=False,
    )
    return plan


def build_review_draft_plan(
    *,
    action: str,
    task_id: str,
    current_version: int,
    restore_version: int | None = None,
) -> OperationPlan:
    """Describe a version-bound review-draft delete or restore preview.

    The target and expected base version are part of the persisted plan rather
    than confirmation input.  This keeps the confirmation endpoint incapable
    of widening or redirecting the planned draft mutation.
    """
    targets: list[dict[str, str]] = [
        {"type": "review_draft", "id": task_id, "label": task_id},
        {
            "type": "review_draft_base_version",
            "id": str(current_version),
            "label": f"base version {current_version}",
        },
    ]
    if action == "review_drafts.restore":
        if restore_version is None:
            raise ValueError("restore_version is required for review draft restoration")
        targets.append(
            {
                "type": "review_draft_restore_version",
                "id": str(restore_version),
                "label": f"restore version {restore_version}",
            }
        )
        summary = f"Restore review draft {task_id} version {restore_version} as a new version."
        warnings = ["The current draft must still match the previewed version before restoration."]
        reversible = True
    elif action == "review_drafts.delete":
        summary = f"Delete review draft {task_id} and its retained history."
        warnings = ["Deleting a review draft also removes its retained version history."]
        reversible = False
    else:
        raise ValueError(f"unsupported review draft action: {action}")

    return build_operation_plan(
        action=action,
        targets=targets,
        summary=summary,
        warnings=warnings,
        expected_version=str(current_version),
        version_snapshot={
            "task_id": task_id,
            "current_version": current_version,
            "restore_version": restore_version,
            "action": action,
        },
        reversible=reversible,
    )


def build_batch_metadata_plan(
    payload: BatchMetadataExecutionPayload,
    question_versions: dict[str, str],
) -> OperationPlan:
    """Persist the resolved metadata writes and every target's version token."""
    if set(question_versions) != set(payload.question_ids):
        raise ValueError("question version snapshot must cover every metadata target")
    version_snapshot = {
        "question_versions": question_versions,
        "execution_payload": payload.model_dump(mode="json"),
    }
    return build_operation_plan(
        action="questions.batch_metadata",
        targets=[{"type": "question", "id": question_id, "label": question_id} for question_id in payload.question_ids],
        summary=f"Apply resolved metadata updates to {len(payload.question_ids)} questions.",
        warnings=["The operation will be rejected if any target question metadata changes before confirmation."],
        expected_version=snapshot_version(version_snapshot),
        version_snapshot=version_snapshot,
        execution_payload=payload,
        reversible=True,
    )


def build_tag_maintenance_plan(
    *,
    question_versions: dict[str, list[str]],
    question_ids: list[str],
    add_tags: list[str],
    remove_tags: list[str],
    merge_map: dict[str, list[str]],
    reason: str,
    create_catalog_tags: bool,
) -> OperationPlan:
    """Persist the resolved tag rewrite and its per-question tag snapshot."""
    if set(question_versions) != set(question_ids):
        raise ValueError("tag version snapshot must cover every changed question")
    version_snapshot = {
        "question_versions": question_versions,
        "tag_maintenance": {
            "question_ids": question_ids,
            "add_tags": add_tags,
            "remove_tags": remove_tags,
            "merge_map": merge_map,
            "reason": reason,
            "create_catalog_tags": create_catalog_tags,
        },
    }
    return build_operation_plan(
        action="questions.tag_maintenance",
        targets=[{"type": "question", "id": question_id, "label": question_id} for question_id in question_ids],
        summary=f"Normalize search tags for {len(question_ids)} questions.",
        warnings=["The operation will be rejected if any planned question tags change before confirmation."],
        expected_version=snapshot_version(version_snapshot),
        version_snapshot=version_snapshot,
        reversible=True,
    )


def build_question_knowledge_point_replace_plan(
    *,
    question_id: str,
    before_links: list[dict[str, Any]],
    replacement_items: list[dict[str, Any]],
    reason: str,
) -> OperationPlan:
    """Persist one question's exact knowledge-point replacement for confirmation."""
    replacement = {
        "question_id": question_id,
        "items": replacement_items,
        "reason": reason,
    }
    version_snapshot = {
        "question_id": question_id,
        "before_links": before_links,
        "knowledge_point_replacement": replacement,
    }
    return build_operation_plan(
        action="questions.knowledge_points.replace",
        targets=[{"type": "question", "id": question_id, "label": question_id}],
        summary=f"Replace knowledge-point links for question {question_id}.",
        warnings=["The replacement is rejected if this question’s knowledge-point links change before confirmation."],
        expected_version=snapshot_version(version_snapshot),
        version_snapshot=version_snapshot,
        reversible=True,
    )
