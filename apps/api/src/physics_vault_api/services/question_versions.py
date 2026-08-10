from __future__ import annotations

import json
from typing import Any

from ..repositories.question_write import QuestionWriteRepository
from ..schemas.question_versions import (
    QuestionVersionDetail,
    QuestionVersionSummary,
    VersionRollbackResponse,
)
from .question_write import QuestionWriteService


class QuestionVersionService:
    """Version-history orchestration over the canonical question write store."""

    def __init__(
        self,
        repository: QuestionWriteRepository,
        question_write_service: QuestionWriteService,
    ) -> None:
        self._repository = repository
        self._question_write_service = question_write_service

    def list(self, question_id: str) -> list[QuestionVersionSummary]:
        return [QuestionVersionSummary.model_validate(item) for item in self._repository.list_versions(question_id)]

    def get(self, question_id: str, version_id: str) -> QuestionVersionDetail:
        return QuestionVersionDetail.model_validate(self._get_owned_version(question_id, version_id))

    def rollback(
        self,
        question_id: str,
        version_id: str,
        *,
        modified_by: str,
    ) -> VersionRollbackResponse:
        version = self._get_owned_version(question_id, version_id)
        snapshot = version.get("snapshot")
        if not isinstance(snapshot, dict) or not snapshot:
            raise ValueError("Version snapshot is empty and cannot be restored")

        result = self._question_write_service.save_batch(
            [self._question_payload(question_id, snapshot)],
            version_modified_by=modified_by,
            version_source="rollback",
            version_change_summary=f"Restored from version {version['version_number']}",
        )
        if result.saved_count == 0:
            raise RuntimeError("Question restore failed: " + "; ".join(result.errors))

        return VersionRollbackResponse(
            question_id=question_id,
            restored_from_version=version_id,
            restored_version_number=int(version["version_number"]),
            message=(
                f"Restored version {version['version_number']} "
                "and recorded the pre-restore state as a new version"
            ),
        )

    def _get_owned_version(self, question_id: str, version_id: str) -> dict[str, Any]:
        version = self._repository.get_version(version_id)
        if version is None:
            raise LookupError("Version not found")
        if version["question_id"] != question_id:
            raise LookupError("Version does not belong to this question")
        return version

    @staticmethod
    def _question_payload(question_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        stem_text = str(snapshot.get("stem_text") or "")
        return {
            "question_id": question_id,
            "question_type": str(snapshot.get("question_type") or "calculation"),
            "title": str(snapshot.get("title") or stem_text.split("\n")[0]),
            "options": _decode_list(snapshot.get("options_json")),
            "answer": str(snapshot.get("answer") or ""),
            "analysis": str(snapshot.get("analysis") or ""),
            "sub_questions": _decode_list(snapshot.get("sub_questions_json")),
            "figures": [],
            "difficulty": snapshot.get("difficulty"),
            "knowledge_point": str(snapshot.get("knowledge_point") or ""),
            "tags": _decode_string_list(snapshot.get("tags_json")),
            "source": str(snapshot.get("source") or ""),
            "review_status": "confirmed",
        }


def _decode_list(value: Any) -> list[dict[str, Any]]:
    decoded = _decode_json(value)
    return [item for item in decoded if isinstance(item, dict)] if isinstance(decoded, list) else []


def _decode_string_list(value: Any) -> list[str]:
    decoded = _decode_json(value)
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []
