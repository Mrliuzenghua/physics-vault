from __future__ import annotations

from ..repositories.question_imports import QuestionImportRepository
from ..repositories.review_queue import ReviewQueueRepository
from ..schemas.question_imports import ImportQuestionRequest, ImportQuestionResponse


class QuestionImportService:
    def __init__(self, repository: QuestionImportRepository, review_queue: ReviewQueueRepository) -> None:
        self._repository = repository
        self._review_queue = review_queue

    def import_question(self, payload: ImportQuestionRequest) -> ImportQuestionResponse:
        data = self._repository.create(payload.model_dump())
        try:
            review_id = self._review_queue.create(
                question_id=data["question_id"],
                queue_type="import_approve",
                status="approved",
                reason=payload.note,
                payload={"reviewer": payload.reviewer, "source": "external_import"},
            )
        except Exception:
            self._repository.delete(data["question_id"])
            raise
        return ImportQuestionResponse(**data, review_id=review_id)
