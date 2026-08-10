"""Application adapters for the shared high-risk operation-plan contract."""

from __future__ import annotations

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mcp_contracts.src.operation_plan import OperationPlan, build_operation_plan

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
