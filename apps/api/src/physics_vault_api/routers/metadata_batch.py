"""Batch metadata completion endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..repositories.operation_plans import OperationPlanRepository
from ..schemas.metadata_batch import (
    BatchMetadataOperationExecutionResponse,
    BatchMetadataPreviewResponse,
    BatchMetadataRequest,
    BatchMetadataResponse,
    ConfirmBatchMetadataOperationRequest,
)
from ..services.metadata_batch import MetadataBatchOperationError, MetadataBatchService
from ..services.operation_plans import (
    OperationPlanError,
    OperationPlanService,
    OperationPlanVersionConflict,
    build_batch_metadata_plan,
)


def build_metadata_batch_router(
    service: MetadataBatchService,
    operation_plan_service: OperationPlanService | None = None,
) -> APIRouter:
    if operation_plan_service is None:
        operation_plan_service = OperationPlanService(OperationPlanRepository())
    router = APIRouter(prefix="/api/questions", tags=["metadata-batch"])

    @router.post(
        "/batch-metadata/preview",
        response_model=BatchMetadataPreviewResponse,
        summary="预览批量元数据写入",
    )
    async def preview_batch_metadata(request: BatchMetadataRequest) -> BatchMetadataPreviewResponse:
        try:
            payload, question_versions, preview = await service.build_operation_payload(request)
            plan = build_batch_metadata_plan(payload, question_versions)
            operation_plan_service.save_preview(plan)
            return BatchMetadataPreviewResponse(preview=preview, operation_plan=plan)
        except MetadataBatchOperationError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "批量元数据预览异常", "detail": str(exc)},
            ) from exc

    @router.post(
        "/batch-metadata/confirm-operation",
        response_model=BatchMetadataOperationExecutionResponse,
        summary="确认已持久化的批量元数据计划",
    )
    async def confirm_batch_metadata_operation(
        request: ConfirmBatchMetadataOperationRequest,
    ) -> BatchMetadataOperationExecutionResponse:
        try:
            result = operation_plan_service.execute(
                request.operation_id,
                version_reader=service.current_operation_version,
                executor=lambda plan: service.execute_operation_payload(
                    plan.execution_payload
                ).model_dump(mode="json"),
            )
            return BatchMetadataOperationExecutionResponse(
                operation_id=result.operation_id,
                status=result.status,
                result=BatchMetadataResponse.model_validate(result.result) if result.result else None,
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
        except MetadataBatchOperationError as exc:
            raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc

    @router.post(
        "/batch-metadata",
        response_model=BatchMetadataResponse,
        summary="批量元数据补全",
        description=(
            "对一批题目统一补全知识点、标签、来源。"
            "支持 AI 自动生成、人工统一覆盖、混合三种模式。"
            "force_overwrite=false 时只补全空字段，true 时覆盖已有值。"
        ),
    )
    async def batch_metadata(request: BatchMetadataRequest) -> BatchMetadataResponse:
        try:
            return await service.process(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "批量元数据处理异常", "detail": str(exc)},
            ) from exc

    return router
