from __future__ import annotations

import json

from ..repositories.question_reviews import QuestionReviewRepository
from ..repositories.review_queue import ReviewQueueRepository
from ..schemas.question_reviews import (
    ProposeFixRequest,
    ProposeFixResponse,
    DecideFixRequest,
    DecideFixResponse,
    FixDetailResponse,
    PendingFixItem,
    RejectedQuestionItem,
    ReportIssueRequest,
    ReportIssueResponse,
    ReviewActionRequest,
    ReviewActionResponse,
    ReviewQueueItem,
)


APPROVED_STATUS = "\u5df2\u5ba1\u6838"
REJECTED_STATUS = "\u5df2\u9a73\u56de"


class QuestionReviewService:
    def __init__(
        self,
        question_repository: QuestionReviewRepository,
        review_queue_repository: ReviewQueueRepository,
    ) -> None:
        self._questions = question_repository
        self._queue = review_queue_repository

    def review(self, question_id: str, payload: ReviewActionRequest) -> ReviewActionResponse:
        current_status = self._questions.get_status(question_id)
        if current_status is None:
            raise LookupError("Question not found")
        status = APPROVED_STATUS if payload.action == "approve" else REJECTED_STATUS
        queue_status = "approved" if payload.action == "approve" else "rejected"
        if not self._questions.set_status(question_id, status):
            raise LookupError("Question not found")
        try:
            review_id = self._queue.create(
                question_id=question_id,
                queue_type="teacher_review",
                status=queue_status,
                reason=payload.reason,
                payload={"reviewer": payload.reviewer, "action": payload.action},
            )
        except Exception:
            self._questions.set_status(question_id, current_status)
            raise
        return ReviewActionResponse(
            question_id=question_id,
            action=payload.action,
            status=status,
            review_id=review_id,
        )

    def propose_fix(self, question_id: str, payload: ProposeFixRequest) -> ProposeFixResponse:
        if self._questions.get_status(question_id) is None:
            raise LookupError("Question not found")
        review_id = self._queue.create(
            question_id=question_id,
            queue_type="ai_fix",
            status="pending",
            reason=payload.reason or payload.summary,
            payload={
                "new_stem_text": payload.new_stem_text,
                "fix_type": payload.fix_type,
                "summary": payload.summary,
                "ai_source": payload.ai_source,
            },
        )
        return ProposeFixResponse(review_id=review_id, question_id=question_id, status="pending")

    def report_issue(self, question_id: str, payload: ReportIssueRequest) -> ReportIssueResponse:
        current_status = self._questions.get_status(question_id)
        if current_status is None:
            raise LookupError("Question not found")
        if not self._questions.set_status(question_id, REJECTED_STATUS):
            raise LookupError("Question not found")
        try:
            review_id = self._queue.create(
                question_id=question_id,
                queue_type="issue_report",
                status="pending",
                reason=payload.description,
                payload={
                    "issue_type": payload.issue_type,
                    "description": payload.description,
                    "reporter": payload.reporter,
                },
            )
        except Exception:
            self._questions.set_status(question_id, current_status)
            raise
        return ReportIssueResponse(review_id=review_id, question_id=question_id, status=REJECTED_STATUS)

    def history(self, question_id: str) -> list[ReviewQueueItem]:
        return [ReviewQueueItem.model_validate(item) for item in self._queue.list_for_question(question_id)]

    def pending_fixes(self) -> list[PendingFixItem]:
        items: list[PendingFixItem] = []
        for row in self._queue.list_by_type_status(queue_type="ai_fix", status="pending"):
            payload = _decode_payload(row["payload_json"])
            context = self._questions.get_context(str(row["entity_id"])) or {}
            items.append(
                PendingFixItem(
                    review_id=row["review_id"],
                    question_id=row["entity_id"],
                    reason=row["reason"],
                    created_at=row["created_at"],
                    fix_type=payload.get("fix_type"),
                    summary=payload.get("summary"),
                    ai_source=payload.get("ai_source"),
                    module=context.get("module"),
                    topic2=context.get("topic2"),
                    topic3=context.get("topic3"),
                    status=context.get("status"),
                )
            )
        return items

    def rejected_questions(self, *, limit: int, offset: int) -> list[RejectedQuestionItem]:
        items: list[RejectedQuestionItem] = []
        for question in self._questions.list_rejected(status=REJECTED_STATUS, limit=limit, offset=offset):
            history = self._queue.list_for_question(str(question["question_id"]))
            relevant = [item for item in history if item["status"] in {"rejected", "pending"}]
            latest = relevant[0] if relevant else None
            items.append(
                RejectedQuestionItem(
                    **question,
                    latest_reason=latest["reason"] if latest else None,
                    latest_queue_type=latest["queue_type"] if latest else None,
                    latest_at=latest["created_at"] if latest else None,
                    pending_fix_count=sum(
                        1
                        for item in history
                        if item["queue_type"] == "ai_fix" and item["status"] == "pending"
                    ),
                )
            )
        return items

    def fix_detail(self, review_id: str) -> FixDetailResponse:
        review = self._get_review(review_id)
        payload = _decode_payload(review["payload_json"])
        context = self._questions.get_context(str(review["entity_id"])) or {}
        return FixDetailResponse(
            review_id=review["review_id"],
            question_id=review["entity_id"],
            queue_type=review["queue_type"],
            status=review["status"],
            reason=review["reason"],
            created_at=review["created_at"],
            fix_type=payload.get("fix_type"),
            summary=payload.get("summary"),
            ai_source=payload.get("ai_source"),
            new_stem_text=payload.get("new_stem_text"),
            current_stem_text=context.get("stem_text"),
        )

    def decide(self, review_id: str, payload: DecideFixRequest) -> DecideFixResponse:
        review = self._get_review(review_id)
        question_id = str(review["entity_id"])
        if payload.action == "reject":
            if not self._queue.update_status(review_id, "rejected"):
                raise LookupError("Review record not found")
            return DecideFixResponse(
                review_id=review_id,
                question_id=question_id,
                action="reject",
                question_status=REJECTED_STATUS,
            )

        proposed = _decode_payload(review["payload_json"])
        new_stem = proposed.get("new_stem_text")
        if not isinstance(new_stem, str) or not new_stem.strip():
            raise ValueError("Review proposal is missing new_stem_text")
        current = self._questions.get_context(question_id)
        if current is None:
            raise LookupError("Question not found")
        if not self._questions.update_stem_and_status(question_id, stem_text=new_stem, status=APPROVED_STATUS):
            raise LookupError("Question not found")
        try:
            if not self._queue.update_status(review_id, "applied"):
                raise RuntimeError("Review record not found during decision")
        except Exception:
            self._questions.update_stem_and_status(
                question_id,
                stem_text=str(current.get("stem_text") or ""),
                status=str(current["status"]),
            )
            raise
        return DecideFixResponse(
            review_id=review_id,
            question_id=question_id,
            action="apply",
            question_status=APPROVED_STATUS,
        )

    def _get_review(self, review_id: str) -> dict:
        review = self._queue.get(review_id)
        if review is None:
            raise LookupError("Review record not found")
        return review


def _decode_payload(raw: object) -> dict:
    try:
        value = json.loads(raw or "{}") if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}
