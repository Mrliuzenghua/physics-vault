from __future__ import annotations

from fastapi import APIRouter

from ..schemas.contracts import IntegerMapResponse
from ..services.question_stats import QuestionStatsService


def build_question_stats_router(service: QuestionStatsService) -> APIRouter:
    """Preserve the read-only statistics contract outside the legacy module."""

    router = APIRouter(tags=["question-stats"])

    @router.get("/stats/questions", response_model=IntegerMapResponse)
    def question_stats() -> dict[str, int]:
        return service.status_counts()

    return router
