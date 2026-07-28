from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.review_save import (
    SaveReviewedQuestionsRequest,
    SaveReviewedQuestionsResponse,
)
from ..services.review_save import ReviewSaveService


def build_review_save_router(
    service: ReviewSaveService | None = None,
) -> APIRouter:
    if service is None:
        service = ReviewSaveService()

    router = APIRouter(prefix="/api/review", tags=["review-save"])

    @router.post(
        "/save",
        response_model=SaveReviewedQuestionsResponse,
        summary="保存校对结果入库",
        description=(
            "将校对工作台中已确认的题目批量写入题库数据库。"
            "仅 review_status 为 'confirmed' 的题目会被保存；"
            "discarded / pending / modified 状态的题目会被跳过。"
        ),
    )
    async def save_reviewed(payload: SaveReviewedQuestionsRequest) -> SaveReviewedQuestionsResponse:
        try:
            return service.save(payload.task_id, payload.questions)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "数据库不可用，请检查数据库文件是否存在", "detail": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "保存失败，请稍后重试", "detail": str(exc)},
            ) from exc

    return router
