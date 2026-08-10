from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.question_details import QuestionAsset, QuestionDetail
from ..services.question_details import QuestionDetailService


def build_question_details_router(service: QuestionDetailService) -> APIRouter:
    router = APIRouter(tags=["question-details"])

    @router.get("/questions/{question_id}", response_model=QuestionDetail)
    def get_question(question_id: str) -> QuestionDetail:
        question = service.get(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="Question not found")
        return question

    @router.get("/questions/{question_id}/assets", response_model=list[QuestionAsset])
    def list_question_assets(question_id: str) -> list[QuestionAsset]:
        return service.list_assets(question_id)

    return router
