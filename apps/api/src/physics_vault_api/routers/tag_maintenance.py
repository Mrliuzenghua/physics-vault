"""Confirmation-gated API endpoints for canonical question tag maintenance."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.tag_maintenance import (
    ConfirmTagMaintenanceOperationRequest,
    TagMaintenanceOperationExecutionResponse,
    TagMaintenancePreviewRequest,
    TagMaintenancePreviewResponse,
)
from ..services.operation_plans import OperationPlanError, OperationPlanVersionConflict
from ..services.tag_maintenance import TagMaintenanceOperationService


def build_tag_maintenance_router(service: TagMaintenanceOperationService) -> APIRouter:
    router = APIRouter(prefix="/api/questions/tags", tags=["tag-maintenance"])

    @router.post("/preview", response_model=TagMaintenancePreviewResponse)
    async def preview_tag_maintenance(
        request: TagMaintenancePreviewRequest,
    ) -> TagMaintenancePreviewResponse:
        result = service.preview(**request.model_dump())
        if not result.get("ok"):
            detail = result.get("error_info") if isinstance(result.get("error_info"), dict) else result
            raise HTTPException(status_code=400, detail=detail)
        return TagMaintenancePreviewResponse.model_validate(result)

    @router.post("/confirm-operation", response_model=TagMaintenanceOperationExecutionResponse)
    async def confirm_tag_maintenance_operation(
        request: ConfirmTagMaintenanceOperationRequest,
    ) -> TagMaintenanceOperationExecutionResponse:
        try:
            result = service.confirm(request.operation_id)
            return TagMaintenanceOperationExecutionResponse(
                operation_id=result.operation_id,
                status=result.status,
                result=result.result,
                error=result.error,
                idempotent=result.idempotent,
            )
        except OperationPlanVersionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "OPERATION_PLAN_VERSION_CONFLICT", "message": str(exc)},
            ) from exc
        except OperationPlanError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "OPERATION_PLAN_NOT_FOUND", "message": str(exc)},
            ) from exc

    return router
