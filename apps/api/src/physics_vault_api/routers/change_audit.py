from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..schemas.contracts import ObjectMapResponse
from pydantic import BaseModel

from ..services.change_audit import ChangeAuditService


class RollbackChangeBatchRequest(BaseModel):
    dry_run: bool = True
    reason: str | None = None
    allow_conflicts: bool = False


def build_change_audit_router(service: ChangeAuditService) -> APIRouter:
    router = APIRouter(prefix="/api/audit", tags=["change-audit"])

    @router.get("/batches", response_model=ObjectMapResponse)
    async def list_batches(
        change_type: str | None = None,
        status: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        return service.list_batches(change_type=change_type, status=status, limit=limit)

    @router.get("/batches/{batch_id}", response_model=ObjectMapResponse)
    async def get_batch(batch_id: str) -> dict[str, Any]:
        result = service.get_batch(batch_id)
        if not result.get("ok"):
            status_code = 404 if result.get("status") == "missing" else 400
            raise HTTPException(status_code=status_code, detail=result.get("error") or "读取变更批次失败")
        return result

    @router.post("/batches/{batch_id}/rollback", response_model=ObjectMapResponse)
    async def rollback_batch(batch_id: str, payload: RollbackChangeBatchRequest) -> dict[str, Any]:
        result = service.rollback_batch(
            batch_id,
            dry_run=payload.dry_run,
            reason=payload.reason,
            allow_conflicts=payload.allow_conflicts,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=409 if result.get("conflict_count") else 400, detail=result)
        return result

    return router
