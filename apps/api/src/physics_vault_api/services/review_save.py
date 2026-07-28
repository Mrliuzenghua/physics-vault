"""Business logic for saving reviewed questions to the database.

Delegates batch-writing to ``QuestionWriteService`` so that the core
upsert logic is shared across all write paths (review, import, migration).
"""

from __future__ import annotations

import logging
from typing import Any

from ..schemas.review_save import (
    ReviewedQuestionPayload,
    SaveResultItem,
    SaveReviewedQuestionsResponse,
)
from .question_write import QuestionWriteService

logger = logging.getLogger(__name__)


class ReviewSaveService:
    """Saves confirmed questions from the review workbench into the database.

    Rules:
    - Only ``review_status == 'confirmed'`` questions are saved.
    - ``discarded`` questions are silently skipped.
    - ``pending`` / ``modified`` questions are also skipped (not confirmed yet).
    """

    def __init__(self, write_service: QuestionWriteService | None = None) -> None:
        self._write = write_service or QuestionWriteService()

    def save(
        self,
        task_id: str,
        questions: list[ReviewedQuestionPayload],
    ) -> SaveReviewedQuestionsResponse:
        """Save confirmed questions and return per-item results."""

        confirmed: list[dict[str, Any]] = []
        skipped: list[SaveResultItem] = []

        for q in questions:
            if q.review_status == "confirmed":
                confirmed.append(q.model_dump())
            else:
                skipped.append(
                    SaveResultItem(
                        draft_question_id=q.question_id,
                        saved_question_id=None,
                        error=f"状态为 '{q.review_status}'，未确认的题目不保存",
                    )
                )

        if not confirmed:
            return SaveReviewedQuestionsResponse(
                saved_count=0,
                skipped_count=len(skipped),
                failed_count=0,
                results=skipped,
            )

        result = self._write.save_batch(confirmed)

        # ── Build per-item results ──
        results: list[SaveResultItem] = list(skipped)
        failed_ids: set[str] = set()
        for err in result.errors:
            # Try to extract question_id from error message
            for q in confirmed:
                qid = q.get("question_id", "")
                if qid and qid in err:
                    failed_ids.add(qid)
                    break

        for q in confirmed:
            qid = q.get("question_id", "")
            if qid in failed_ids:
                results.append(
                    SaveResultItem(
                        draft_question_id=qid,
                        saved_question_id=None,
                        error="写入失败（校验未通过或数据库异常）",
                    )
                )
            else:
                results.append(
                    SaveResultItem(
                        draft_question_id=qid,
                        saved_question_id=qid,
                        error=None,
                    )
                )

        success_count = result.saved_count
        failed_count = result.received_count - result.saved_count

        return SaveReviewedQuestionsResponse(
            saved_count=success_count,
            skipped_count=len(skipped),
            failed_count=failed_count,
            results=results,
        )
