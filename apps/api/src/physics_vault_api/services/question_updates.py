from __future__ import annotations

from typing import Any

from ..repositories.question_details import QuestionDetailRepository
from ..schemas.question_details import QuestionDetail
from .question_write import QuestionWriteService


class QuestionUpdateService:
    def __init__(self, details: QuestionDetailRepository, writer: QuestionWriteService) -> None:
        self._details = details
        self._writer = writer

    def update(self, question_id: str, patch: dict[str, Any]) -> QuestionDetail:
        baseline = self._details.get_write_payload(question_id)
        if baseline is None:
            raise LookupError("Question not found")
        merged = {**baseline, **patch, "question_id": question_id}
        if "type" in patch and "question_type" not in patch:
            merged["question_type"] = patch["type"]
        if not patch.get("figures"):
            merged["figures"] = baseline["figures"]
        result = self._writer.save_batch([merged])
        if result.saved_count == 0:
            raise RuntimeError("Question save failed: " + "; ".join(result.errors))
        updated = self._details.get(question_id)
        if updated is None:
            raise RuntimeError("Question could not be read after save")
        return updated
