from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.similar_questions import SimilarQuestionsResponse
from ..services.similar_questions import SimilarQuestionsService


def build_similar_questions_router(
    service: SimilarQuestionsService | None = None,
) -> APIRouter:
    if service is None:
        service = SimilarQuestionsService()

    router = APIRouter(prefix="/api/questions", tags=["similar-questions"])

    @router.get(
        "/{question_id}/similar",
        response_model=SimilarQuestionsResponse,
        summary="查找相似题",
        description=(
            "基于题型、知识点、难度、标签和题干关键词的规则型相似题查找。"
            "不依赖向量检索，使用可解释的结构化字段评分。"
        ),
    )
    async def find_similar(
        question_id: str,
        limit: int = Query(default=10, ge=1, le=20, description="返回结果数上限"),
        same_question_type: bool = Query(
            default=False, description="候选集限定为同题型"
        ),
        same_knowledge_point: bool = Query(
            default=False, description="候选集限定为同知识点"
        ),
        difficulty_tolerance: int = Query(
            default=2, ge=0, le=5, description="难度容忍范围（0-5）"
        ),
    ) -> SimilarQuestionsResponse:
        try:
            return service.find_similar(
                question_id=question_id,
                limit=limit,
                same_question_type=same_question_type,
                same_knowledge_point=same_knowledge_point,
                difficulty_tolerance=difficulty_tolerance,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "相似题查询失败", "detail": str(exc)},
            ) from exc

    return router
