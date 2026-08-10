from __future__ import annotations

from ..repositories.question_details import QuestionDetailRepository
from ..schemas.question_details import QuestionAsset, QuestionDetail


class QuestionDetailService:
    def __init__(self, repository: QuestionDetailRepository) -> None:
        self._repository = repository

    def get(self, question_id: str) -> QuestionDetail | None:
        return self._repository.get(question_id)

    def list_assets(self, question_id: str) -> list[QuestionAsset]:
        return self._repository.list_assets(question_id)
