from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas.question_details import QuestionDetail
from ..services.question_updates import QuestionUpdateService


def build_question_updates_router(service: QuestionUpdateService) -> APIRouter:
    router = APIRouter(tags=["question-updates"])

    @router.put("/questions/{question_id}", response_model=QuestionDetail)
    def update_question(question_id: str, payload: dict[str, Any]) -> QuestionDetail:
        try:
            return service.update(question_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
