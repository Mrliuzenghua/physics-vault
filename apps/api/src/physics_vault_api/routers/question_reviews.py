from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.question_reviews import (
    DecideFixRequest,
    DecideFixResponse,
    FixDetailResponse,
    PendingFixItem,
    ProposeFixRequest,
    ProposeFixResponse,
    RejectedQuestionItem,
    ReportIssueRequest,
    ReportIssueResponse,
    ReviewActionRequest,
    ReviewActionResponse,
    ReviewQueueItem,
)
from ..services.question_reviews import QuestionReviewService


def build_question_reviews_router(service: QuestionReviewService) -> APIRouter:
    router = APIRouter(tags=["question-reviews"])

    @router.post("/questions/{question_id}/review", response_model=ReviewActionResponse)
    def review_question(question_id: str, payload: ReviewActionRequest) -> ReviewActionResponse:
        try:
            return service.review(question_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/questions/{question_id}/propose-fix", response_model=ProposeFixResponse)
    def propose_fix(question_id: str, payload: ProposeFixRequest) -> ProposeFixResponse:
        try:
            return service.propose_fix(question_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/questions/{question_id}/report-issue", response_model=ReportIssueResponse)
    def report_issue(question_id: str, payload: ReportIssueRequest) -> ReportIssueResponse:
        try:
            return service.report_issue(question_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/questions/{question_id}/review-history", response_model=list[ReviewQueueItem])
    def review_history(question_id: str) -> list[ReviewQueueItem]:
        return service.history(question_id)

    @router.get("/review-queue/pending-fixes", response_model=list[PendingFixItem])
    def list_pending_fixes() -> list[PendingFixItem]:
        return service.pending_fixes()

    @router.get("/review-queue/rejected", response_model=list[RejectedQuestionItem])
    def list_rejected_questions(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[RejectedQuestionItem]:
        return service.rejected_questions(limit=limit, offset=offset)

    @router.get("/review-queue/{review_id}", response_model=FixDetailResponse)
    def get_fix_detail(review_id: str) -> FixDetailResponse:
        try:
            return service.fix_detail(review_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/review-queue/{review_id}/decide", response_model=DecideFixResponse)
    def decide_fix(review_id: str, payload: DecideFixRequest) -> DecideFixResponse:
        try:
            return service.decide(review_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
