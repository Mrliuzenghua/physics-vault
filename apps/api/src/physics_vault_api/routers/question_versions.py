from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.question_versions import (
    QuestionVersionDetail,
    QuestionVersionSummary,
    VersionRollbackRequest,
    VersionRollbackResponse,
)
from ..services.question_versions import QuestionVersionService


def build_question_versions_router(service: QuestionVersionService) -> APIRouter:
    router = APIRouter(tags=["question-versions"])

    @router.get("/questions/{question_id}/versions", response_model=list[QuestionVersionSummary])
    def list_question_versions(question_id: str) -> list[QuestionVersionSummary]:
        return service.list(question_id)

    @router.get(
        "/questions/{question_id}/versions/{version_id}",
        response_model=QuestionVersionDetail,
    )
    def get_question_version(question_id: str, version_id: str) -> QuestionVersionDetail:
        try:
            return service.get(question_id, version_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/questions/{question_id}/versions/{version_id}/rollback",
        response_model=VersionRollbackResponse,
    )
    def rollback_question_version(
        question_id: str,
        version_id: str,
        body: VersionRollbackRequest | None = None,
    ) -> VersionRollbackResponse:
        try:
            return service.rollback(
                question_id,
                version_id,
                modified_by=(body.modified_by if body else "teacher"),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
