from __future__ import annotations

from ..repositories.papers import PaperRepository
from ..schemas.papers import PaperDetail, PaperQuestionSummary, PaperSummary


class PaperService:
    def __init__(self, repository: PaperRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        year: int | None,
        region: str | None,
        exam_type: str | None,
        query: str | None,
        subject: str,
        limit: int,
        offset: int,
    ) -> list[PaperSummary]:
        return self._repository.list(
            year=year,
            region=region,
            exam_type=exam_type,
            query=query,
            subject=subject,
            limit=limit,
            offset=offset,
        )

    def get(self, paper_id: str) -> PaperDetail | None:
        return self._repository.get(paper_id)

    def list_questions(self, paper_id: str) -> list[PaperQuestionSummary]:
        return self._repository.list_questions(paper_id)
