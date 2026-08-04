from __future__ import annotations

from ..repositories.paper_drafts import PaperDraftConflictError, PaperDraftRepository
from ..schemas.paper_drafts import (
    PaperDraftItem,
    PaperDraftListResponse,
    PaperDraftResponse,
    PaperDraftSummary,
    PaperDraftUpsertRequest,
)
class PaperDraftService:
    def __init__(self, repository: PaperDraftRepository | None = None) -> None:
        self._repo = repository or PaperDraftRepository()

    def list(self, limit: int = 30) -> PaperDraftListResponse:
        rows = self._repo.list(limit=limit)
        return PaperDraftListResponse(items=[PaperDraftSummary(**row) for row in rows])

    def get(self, draft_id: str) -> PaperDraftResponse:
        row = self._repo.get(draft_id)
        if row is None:
            raise ValueError(f"试卷草稿不存在: {draft_id}")
        return PaperDraftResponse(**row)

    def get_latest(self) -> PaperDraftResponse | None:
        row = self._repo.get_latest()
        return PaperDraftResponse(**row) if row else None

    def save(self, request: PaperDraftUpsertRequest) -> PaperDraftResponse:
        normalized_items = [
            item.model_copy(update={"position": index})
            for index, item in enumerate(request.items)
        ]
        total_score = sum((item.score or 0) for item in normalized_items)
        question_count = sum(1 for item in normalized_items if item.type == "question")
        row = self._repo.upsert(
            draft_id=request.id,
            base_updated_at=request.base_updated_at,
            title=request.title.strip() or "未命名试卷",
            subtitle=request.subtitle,
            source=request.source,
            status=request.status,
            items=[item.model_dump() for item in normalized_items],
            metadata=request.metadata,
            quality_report=request.quality_report,
            question_count=question_count,
            item_count=len(normalized_items),
            total_score=total_score,
        )
        return PaperDraftResponse(**row)

    def delete(self, draft_id: str) -> bool:
        return self._repo.delete(draft_id)
