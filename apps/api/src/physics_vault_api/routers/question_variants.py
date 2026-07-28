"""HTTP endpoint for question variant generation.

This is a **business-facing** endpoint (``/api/ai/question-variants/generate``),
distinct from the low-level MCP management endpoints in ``routers/mcp.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.question_variants import (
    GenerateQuestionVariantsRequest,
    GenerateQuestionVariantsResponse,
)
from ..services.question_variants import QuestionVariantService


def build_question_variants_router(service: QuestionVariantService) -> APIRouter:
    router = APIRouter(prefix="/api/ai/question-variants", tags=["ai-question-variants"])

    @router.post(
        "/generate",
        response_model=GenerateQuestionVariantsResponse,
        summary="生成变式题",
        description=(
            "基于已有题目生成变式题。支持改条件、改设问、换数值、换场景、"
            "升难度、降难度六种模式。"
            "若 AI 被禁用或不可用，返回 generated=False 并附带警告说明。"
        ),
    )
    async def generate_question_variants(
        request: GenerateQuestionVariantsRequest,
    ) -> GenerateQuestionVariantsResponse:
        try:
            return await service.generate_variants(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "变式题生成服务异常，请稍后重试", "detail": str(exc)},
            ) from exc

    return router
