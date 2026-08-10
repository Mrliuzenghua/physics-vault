"""Durable post-lesson reflections shared by classroom, dashboard and MCP."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..paths import project_root

_STORE_FILE = project_root() / "data" / "config" / "lesson_reflections.json"
_MAX_REFLECTIONS = 1000


class LessonReflectionConflictError(ValueError):
    """The reflection changed after the caller last read it."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_reflections() -> list[dict[str, Any]]:
    if not _STORE_FILE.is_file():
        return []
    try:
        value = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, dict) and str(item.get("id") or "").strip()]


def _write_reflections(reflections: list[dict[str, Any]]) -> None:
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _STORE_FILE.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(reflections, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, _STORE_FILE)


def _normalize(reflection: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    result = deepcopy(reflection)
    now = _now()
    result["id"] = str(result.get("id") or "").strip()
    result["projectId"] = str(result.get("projectId") or "").strip()
    result["projectTitle"] = str(result.get("projectTitle") or "")
    try:
        result["rating"] = min(5, max(1, int(result.get("rating") or 4)))
    except (TypeError, ValueError):
        result["rating"] = 4
    result["completed"] = bool(result.get("completed"))
    result["highlights"] = str(result.get("highlights") or "")
    result["followUp"] = str(result.get("followUp") or "")
    completed_ids = result.get("completedFollowUpTaskIds")
    if not isinstance(completed_ids, list):
        completed_ids = []
    result["completedFollowUpTaskIds"] = list(dict.fromkeys(
        str(item).strip() for item in completed_ids if str(item).strip()
    ))[:100]
    try:
        result["attendedPages"] = max(0, int(result.get("attendedPages") or 0))
    except (TypeError, ValueError):
        result["attendedPages"] = 0
    result["createdAt"] = (existing or {}).get("createdAt") or result.get("createdAt") or now
    result["updatedAt"] = now
    return result


def list_lesson_reflections(project_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    clean_project_id = str(project_id or "").strip()
    reflections = [
        deepcopy(item)
        for item in _read_reflections()
        if not clean_project_id or str(item.get("projectId") or "") == clean_project_id
    ]
    reflections.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return reflections[: max(1, min(int(limit or 100), 500))]


def get_lesson_reflection(reflection_id: str) -> dict[str, Any] | None:
    clean_id = str(reflection_id or "").strip()
    return next((deepcopy(item) for item in _read_reflections() if str(item.get("id")) == clean_id), None)


def save_lesson_reflection(
    reflection: dict[str, Any],
    *,
    base_updated_at: str | None = None,
) -> dict[str, Any]:
    incoming = deepcopy(reflection)
    reflection_id = str(incoming.get("id") or "").strip()
    project_id = str(incoming.get("projectId") or "").strip()
    if not reflection_id or not project_id:
        raise ValueError("reflection.id and reflection.projectId are required")

    reflections = _read_reflections()
    existing = next((item for item in reflections if str(item.get("id")) == reflection_id), None)
    current_updated_at = str(existing.get("updatedAt") or "") if existing else ""
    if existing and base_updated_at is not None and current_updated_at != str(base_updated_at):
        raise LessonReflectionConflictError("课后复盘已被其他操作更新，请刷新后重试")

    # A repeated request with the same timestamp and content is safe to retry.
    if existing and base_updated_at is not None and str(incoming.get("updatedAt") or "") == current_updated_at:
        return deepcopy(existing)

    next_reflection = _normalize(incoming, existing)
    if existing:
        reflections[reflections.index(existing)] = next_reflection
    else:
        reflections.insert(0, next_reflection)
    reflections.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    _write_reflections(reflections[:_MAX_REFLECTIONS])
    return deepcopy(next_reflection)
