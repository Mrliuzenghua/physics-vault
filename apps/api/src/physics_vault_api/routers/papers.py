from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.papers import PaperDetail, PaperQuestionSummary, PaperSummary
from ..services.papers import PaperService


def build_papers_router(service: PaperService) -> APIRouter:
    router = APIRouter(tags=["papers"])

    @router.get("/papers", response_model=list[PaperSummary])
    def list_papers(
        year: int | None = None,
        region: str | None = None,
        exam_type: str | None = None,
        q: str | None = Query(default=None, description="Search in paper name or paper id"),
        subject: str = "PHY",
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[PaperSummary]:
        return service.list(year=year, region=region, exam_type=exam_type, query=q, subject=subject, limit=limit, offset=offset)

    @router.get("/papers/{paper_id}", response_model=PaperDetail)
    def get_paper(paper_id: str) -> PaperDetail:
        paper = service.get(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        return paper

    @router.get("/papers/{paper_id}/questions", response_model=list[PaperQuestionSummary])
    def list_paper_questions(paper_id: str) -> list[PaperQuestionSummary]:
        return service.list_questions(paper_id)

    return router
