from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.analysis_batch import (
    BatchGenerateAnalysisRequest,
    BatchGenerateAnalysisResponse,
)
from ..services.analysis_batch import AnalysisBatchService


def build_analysis_batch_router(service: AnalysisBatchService) -> APIRouter:
    router = APIRouter(prefix="/api/ai", tags=["ai-batch"])

    @router.post(
        "/analysis/batch-generate",
        response_model=BatchGenerateAnalysisResponse,
        summary="批量生成题目解析",
        description=(
            "对一批题目统一生成解析。单题失败不影响其他题。"
            "若 force_regenerate=false 且题目已有解析，则自动跳过。"
        ),
    )
    async def batch_generate_analysis(
        request: BatchGenerateAnalysisRequest,
    ) -> BatchGenerateAnalysisResponse:
        try:
            return await service.generate_batch(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "批量解析生成失败", "detail": str(exc)},
            ) from exc

    return router
