"""Business logic for saving reviewed questions to the database.

Delegates batch-writing to ``QuestionWriteService`` so that the core
upsert logic is shared across all write paths (review, import, migration).
"""

from __future__ import annotations

import logging
import json
import sqlite3
from typing import Any

from ..paths import default_db_path
from ..schemas.review_save import (
    ReviewedKnowledgePayload,
    ReviewedQuestionPayload,
    SaveResultItem,
    SaveReviewedKnowledgeResponse,
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

    def save_knowledge(
        self,
        task_id: str,
        knowledge_drafts: list[ReviewedKnowledgePayload],
    ) -> SaveReviewedKnowledgeResponse:
        """Save confirmed knowledge-point drafts into the formal knowledge table."""

        del task_id
        results: list[SaveResultItem] = []
        saved_count = 0
        skipped_count = 0
        failed_count = 0

        with sqlite3.connect(default_db_path()) as conn:
            for draft in knowledge_drafts:
                if draft.review_status != "confirmed":
                    skipped_count += 1
                    results.append(
                        SaveResultItem(
                            draft_question_id=draft.draft_id,
                            saved_question_id=None,
                            error=f"状态为 '{draft.review_status}'，未确认的知识点不保存",
                        )
                    )
                    continue

                topic3_id = (draft.topic3_id or draft.draft_id).strip()
                topic3_name = draft.topic3_name.strip()
                if not topic3_id or not topic3_name:
                    failed_count += 1
                    results.append(
                        SaveResultItem(
                            draft_question_id=draft.draft_id,
                            saved_question_id=None,
                            error="缺少知识点 ID 或知识点名称",
                        )
                    )
                    continue

                note = json.dumps(
                    {
                        "definition": draft.definition,
                        "formula": draft.formula,
                        "key_summary": draft.key_summary,
                        "error_prone": draft.error_prone,
                        "example_analysis": draft.example_analysis,
                        "tags": draft.tags,
                        "raw_text": draft.raw_text,
                    },
                    ensure_ascii=False,
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO knowledge_points (
                            topic3_id, topic3_name, topic2_id, topic2_name,
                            topic1_id, topic1_name, source_chapter, status, note, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'))
                        ON CONFLICT(topic3_id) DO UPDATE SET
                            topic3_name = excluded.topic3_name,
                            topic2_id = excluded.topic2_id,
                            topic2_name = excluded.topic2_name,
                            topic1_id = excluded.topic1_id,
                            topic1_name = excluded.topic1_name,
                            source_chapter = excluded.source_chapter,
                            status = 'active',
                            note = excluded.note,
                            updated_at = datetime('now')
                        """,
                        (
                            topic3_id,
                            topic3_name,
                            draft.topic2_id.strip() or "uncategorized",
                            draft.topic2_name.strip() or "未分类",
                            draft.topic1_id.strip() or "uncategorized",
                            draft.topic1_name.strip() or "未分类",
                            draft.source_chapter.strip() or None,
                            note,
                        ),
                    )
                    saved_count += 1
                    results.append(
                        SaveResultItem(
                            draft_question_id=draft.draft_id,
                            saved_question_id=topic3_id,
                            error=None,
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive per-item failure
                    logger.exception("Failed to save reviewed knowledge draft %s", draft.draft_id)
                    failed_count += 1
                    results.append(
                        SaveResultItem(
                            draft_question_id=draft.draft_id,
                            saved_question_id=None,
                            error=str(exc),
                        )
                    )

        return SaveReviewedKnowledgeResponse(
            saved_count=saved_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            results=results,
        )
