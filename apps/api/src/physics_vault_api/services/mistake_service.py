"""Mistake (错题) marking service — mark, unmark, batch, and query."""

from __future__ import annotations

import logging
from typing import Any

from ..repositories.question_write import QuestionWriteRepository

logger = logging.getLogger(__name__)


class MistakeService:
    """Business logic for mistake-question marking."""

    def __init__(self, repo: QuestionWriteRepository) -> None:
        self._repo = repo
        self._repo.ensure_mistake_column()

    # ── Single operations ─────────────────────────────────────────

    def mark(self, question_id: str) -> dict[str, Any]:
        ok = self._repo.set_mistake_status(question_id, True)
        if not ok:
            return {"question_id": question_id, "status": "skipped", "message": "题目不存在"}
        return {"question_id": question_id, "status": "updated", "message": "已标记为错题"}

    def unmark(self, question_id: str) -> dict[str, Any]:
        ok = self._repo.set_mistake_status(question_id, False)
        if not ok:
            return {"question_id": question_id, "status": "skipped", "message": "题目不存在"}
        return {"question_id": question_id, "status": "updated", "message": "已取消错题标记"}

    # ── Batch operations ──────────────────────────────────────────

    def batch_mark(self, question_ids: list[str]) -> dict[str, Any]:
        counts = self._repo.batch_set_mistake_status(question_ids, True)
        return {
            "total": len(question_ids),
            "updated": counts["updated"],
            "skipped": counts["skipped"],
            "failed": counts["failed"],
        }

    def batch_unmark(self, question_ids: list[str]) -> dict[str, Any]:
        counts = self._repo.batch_set_mistake_status(question_ids, False)
        return {
            "total": len(question_ids),
            "updated": counts["updated"],
            "skipped": counts["skipped"],
            "failed": counts["failed"],
        }

    # ── Query ─────────────────────────────────────────────────────

    def list_mistakes(self) -> list[str]:
        return self._repo.get_mistake_question_ids()

    def count_mistakes(self) -> int:
        return len(self._repo.get_mistake_question_ids())
