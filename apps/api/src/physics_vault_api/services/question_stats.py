from __future__ import annotations

from ..repositories.question_stats import QuestionStatsRepository


class QuestionStatsService:
    def __init__(self, repository: QuestionStatsRepository) -> None:
        self._repository = repository

    def status_counts(self) -> dict[str, int]:
        return self._repository.status_counts()
