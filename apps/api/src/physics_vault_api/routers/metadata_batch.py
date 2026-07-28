"""Batch metadata completion endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.metadata_batch import BatchMetadataRequest, BatchMetadataResponse
from ..services.metadata_batch import MetadataBatchService


def build_metadata_batch_router(service: MetadataBatchService) -> APIRouter:
    router = APIRouter(prefix="/api/questions", tags=["metadata-batch"])

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
