"""Business logic for question annotations."""

from __future__ import annotations

from typing import Any

from ..repositories.annotation_repo import AnnotationRepository


class AnnotationService:
    def __init__(self, repo: AnnotationRepository | None = None) -> None:
        self._repo = repo or AnnotationRepository()

    def list(self, question_id: str) -> list[dict[str, Any]]:
        return self._repo.list_by_question(question_id)

    def get(self, annotation_id: str) -> dict[str, Any] | None:
        return self._repo.get(annotation_id)

    def create(self, entry: dict[str, Any]) -> dict[str, Any]:
        return self._repo.create(entry)

    def update(self, annotation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        result = self._repo.update(annotation_id, patch)
        if result is None:
            raise ValueError(f"批注不存在: {annotation_id}")
        return result

    def delete(self, annotation_id: str) -> dict[str, str]:
        ok = self._repo.delete(annotation_id)
        if not ok:
            raise ValueError(f"批注不存在: {annotation_id}")
        return {"status": "deleted", "annotation_id": annotation_id}
