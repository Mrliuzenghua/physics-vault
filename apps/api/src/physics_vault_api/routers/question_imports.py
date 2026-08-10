from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.question_imports import ImportQuestionRequest, ImportQuestionResponse
from ..services.question_imports import QuestionImportService


def build_question_imports_router(service: QuestionImportService) -> APIRouter:
    router = APIRouter(tags=["question-imports"])

    @router.post("/questions/import", response_model=ImportQuestionResponse)
    def import_question(payload: ImportQuestionRequest) -> ImportQuestionResponse:
        try:
            return service.import_question(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
