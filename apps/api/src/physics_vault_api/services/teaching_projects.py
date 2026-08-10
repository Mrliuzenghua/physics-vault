"""Durable teaching-project snapshots shared by web, MCP and export jobs."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..paths import project_root

_STORE_FILE = project_root() / "data" / "config" / "teaching_projects.json"
_MAX_VERSIONS = 30


class TeachingProjectConflictError(ValueError):
    """The project changed after the caller last read it."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_projects() -> list[dict[str, Any]]:
    if not _STORE_FILE.is_file():
        return []
    try:
        value = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, dict) and str(item.get("id") or "").strip()]


def _write_projects(projects: list[dict[str, Any]]) -> None:
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _STORE_FILE.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, _STORE_FILE)


def _project_revision(project: dict[str, Any]) -> int:
    try:
        return max(0, int(project.get("contentRevision") or 0))
    except (TypeError, ValueError):
        return 0


def _artifact_status(project: dict[str, Any], key: str) -> str:
    artifact = project.get(key)
    return str(artifact.get("status") or "not_created") if isinstance(artifact, dict) else "not_created"


def _summary(project: dict[str, Any]) -> dict[str, Any]:
    content = project.get("content") if isinstance(project.get("content"), dict) else {}
    nodes = content.get("nodes") if isinstance(content.get("nodes"), list) else []
    question_count = sum(1 for node in nodes if isinstance(node, dict) and node.get("type") == "question")
    return {
        "id": str(project.get("id") or ""),
        "title": str(project.get("title") or content.get("meta", {}).get("title") or "未命名教学项目"),
        "projectType": project.get("projectType") or "lesson",
        "status": project.get("status") or "draft",
        "contentRevision": _project_revision(project),
        "questionCount": question_count,
        "handoutStatus": _artifact_status(project, "handout"),
        "slidesStatus": _artifact_status(project, "slides"),
        "createdAt": project.get("createdAt") or "",
        "updatedAt": project.get("updatedAt") or "",
        "versionCount": len(project.get("versions") or []),
    }


def _version_snapshot(project: dict[str, Any], version: int, created_at: str) -> dict[str, Any]:
    return {
        "version": version,
        "versionId": f"{project['id']}-v{version}",
        "contentRevision": _project_revision(project),
        "createdAt": created_at,
        "project": deepcopy({key: value for key, value in project.items() if key != "versions"}),
    }


def _comparable_project(project: dict[str, Any]) -> dict[str, Any]:
    """Remove storage and transport metadata before idempotency comparison."""
    volatile = {
        "versions",
        "projectSnapshot",
        "updatedAt",
        "createdAt",
        "currentVersion",
        "document_kind",
        "summary",
        "remoteUpdatedAt",
        "remoteSyncState",
    }
    return {key: value for key, value in project.items() if key not in volatile}


def list_teaching_projects(limit: int = 100) -> list[dict[str, Any]]:
    projects = sorted(_read_projects(), key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return [_summary(item) for item in projects[: max(1, min(int(limit or 100), 200))]]


def get_teaching_project(project_id: str) -> dict[str, Any] | None:
    clean_id = str(project_id or "").strip()
    for project in _read_projects():
        if str(project.get("id")) == clean_id:
            result = deepcopy(project)
            result["document_kind"] = "teaching_project"
            result["summary"] = _summary(result)
            return result
    return None


def save_teaching_project(
    project: dict[str, Any],
    *,
    base_updated_at: str | None = None,
) -> dict[str, Any]:
    incoming = deepcopy(project)
    project_id = str(incoming.get("id") or "").strip()
    if not project_id:
        raise ValueError("project.id is required")

    projects = _read_projects()
    existing = next((item for item in projects if str(item.get("id")) == project_id), None)
    current_updated_at = str(existing.get("updatedAt") or "") if existing else ""
    if existing and base_updated_at is not None and current_updated_at != str(base_updated_at):
        raise TeachingProjectConflictError("教学项目已被其他操作更新，请刷新后重试。")

    now = _now()
    incoming["id"] = project_id
    incoming["createdAt"] = (existing or {}).get("createdAt") or incoming.get("createdAt") or now
    incoming["updatedAt"] = now
    incoming["status"] = incoming.get("status") or "draft"
    incoming["contentRevision"] = _project_revision(incoming)

    previous_versions = [item for item in (existing or {}).get("versions", []) if isinstance(item, dict)]
    previous_project = existing.get("projectSnapshot") if isinstance(existing, dict) else None
    has_changed = existing is None or _comparable_project(previous_project or {}) != _comparable_project(incoming)
    if existing and not has_changed:
        result = deepcopy(existing)
        result["document_kind"] = "teaching_project"
        result["summary"] = _summary(result)
        return result

    next_version = int((existing or {}).get("currentVersion") or 0) + 1
    snapshot = _version_snapshot(incoming, next_version, now)
    versions = (previous_versions + [snapshot])[-_MAX_VERSIONS:]
    incoming["currentVersion"] = next_version
    incoming["versions"] = versions
    incoming["projectSnapshot"] = deepcopy(_comparable_project(incoming))

    if existing:
        projects[projects.index(existing)] = incoming
    else:
        projects.insert(0, incoming)
    _write_projects(projects)
    result = deepcopy(incoming)
    result["document_kind"] = "teaching_project"
    result["summary"] = _summary(result)
    return result


def archive_teaching_project(project_id: str, *, base_updated_at: str | None = None) -> dict[str, Any] | None:
    project = get_teaching_project(project_id)
    if not project:
        return None
    if base_updated_at is not None and str(project.get("updatedAt") or "") != str(base_updated_at):
        raise TeachingProjectConflictError("教学项目已被其他操作更新，请刷新后重试。")
    project.pop("document_kind", None)
    project.pop("summary", None)
    project["status"] = "archived"
    project.pop("versions", None)
    project.pop("projectSnapshot", None)
    return save_teaching_project(project, base_updated_at=base_updated_at)


def duplicate_teaching_project(project_id: str, *, title: str | None = None) -> dict[str, Any] | None:
    source = get_teaching_project(project_id)
    if not source:
        return None
    source.pop("document_kind", None)
    source.pop("summary", None)
    source.pop("versions", None)
    source.pop("projectSnapshot", None)
    source.pop("currentVersion", None)
    new_id = f"{project_id}-copy-{uuid4().hex[:8]}"
    source["id"] = new_id
    source["title"] = (title or f"{source.get('title') or '未命名教学项目'}（副本）").strip()
    source["status"] = "draft"
    source["createdAt"] = _now()
    source["updatedAt"] = source["createdAt"]
    for key in ("handout", "slides"):
        artifact = source.get(key)
        if not isinstance(artifact, dict):
            continue
        artifact["id"] = f"{key}-{new_id}"
        artifact["projectId"] = new_id
        artifact["status"] = "draft"
        artifact.pop("publishedSnapshot", None)
    return save_teaching_project(source)
