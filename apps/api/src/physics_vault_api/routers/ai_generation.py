"""HTTP endpoints for AI-powered analysis and knowledge generation.

These are **business-facing** endpoints (``/api/ai/*``), distinct from the
low-level MCP management endpoints in ``routers/mcp.py`` (``/api/mcp/*``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.ai_generation import (
    GenerateAnalysisRequest,
    GenerateAnalysisResponse,
    GenerateKnowledgeRequest,
    GenerateKnowledgeResponse,
)
from ..services.ai_generation import AiGenerationService


def build_ai_generation_router(service: AiGenerationService) -> APIRouter:
    router = APIRouter(prefix="/api/ai", tags=["ai-generation"])

    @router.post(
        "/analysis/generate",
        response_model=GenerateAnalysisResponse,
        summary="生成题目解析",
        description=(
            "根据题目结构化数据生成详细解析。"
            "支持课堂简析、自学详解、考标解析三种风格。"
            "若 AI 被禁用或不可用，返回 generated=False 并附带警告说明。"
        ),
    )
    async def generate_analysis(
        request: GenerateAnalysisRequest,
    ) -> GenerateAnalysisResponse:
        try:
            return await service.generate_analysis(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "解析生成服务异常，请稍后重试", "detail": str(exc)},
            ) from exc

    @router.post(
        "/knowledge/generate",
        response_model=GenerateKnowledgeResponse,
        summary="生成知识点专题内容",
        description=(
            "根据知识点列表生成专题讲解内容。"
            "支持短/中/长三种篇幅。"
            "相同知识点组合（顺序无关）会自动命中缓存。"
            "设置 force_regenerate=true 可跳过缓存强制重新生成。"
        ),
    )
    async def generate_knowledge(
        request: GenerateKnowledgeRequest,
    ) -> GenerateKnowledgeResponse:
        try:
            return await service.generate_knowledge(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "知识点生成服务异常，请稍后重试", "detail": str(exc)},
            ) from exc

    # ── Cache management ──────────────────────────────────────────

    @router.delete(
        "/knowledge/cache",
        summary="清空知识点生成缓存",
        description="删除全部知识点生成缓存条目。下次请求相同知识点将重新调用 AI。",
    )
    async def clear_knowledge_cache() -> dict[str, int]:
        count = service.clear_knowledge_cache()
        return {"deleted": count}

    @router.delete(
        "/knowledge/cache/{cache_key}",
        summary="删除单个缓存条目",
        description="按缓存键删除单条知识点生成缓存。",
    )
    async def delete_knowledge_cache_entry(cache_key: str) -> dict[str, bool]:
        ok = service.delete_knowledge_cache_entry(cache_key)
        if not ok:
            raise HTTPException(status_code=404, detail="缓存条目不存在")
        return {"deleted": True}

    return router
