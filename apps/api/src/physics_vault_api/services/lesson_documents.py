"""Durable saved-handout documents shared by the web app and MCP."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..paths import project_root

_STORE_FILE = project_root() / "data" / "config" / "saved_handouts.json"
_MAX_VERSIONS = 30


def _read_documents() -> list[dict[str, Any]]:
    if not _STORE_FILE.is_file():
        return []
    try:
        value = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, dict) and item.get("id")] if isinstance(value, list) else []


def _write_documents(documents: list[dict[str, Any]]) -> None:
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _STORE_FILE.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, _STORE_FILE)


def _summary(document: dict[str, Any]) -> dict[str, Any]:
    package = document.get("lessonPackage") if isinstance(document.get("lessonPackage"), dict) else {}
    questions = package.get("questions") if isinstance(package.get("questions"), list) else []
    knowledge = package.get("knowledgeCards") if isinstance(package.get("knowledgeCards"), list) else []
    nodes = package.get("nodes") if isinstance(package.get("nodes"), list) else []
    return {
        "id": str(document.get("id") or package.get("id") or ""),
        "title": str(document.get("title") or package.get("title") or "未命名讲义"),
        "subtitle": str(document.get("subtitle") or package.get("subtitle") or ""),
        "document_kind": "saved_handout",
        "source_workbench_id": document.get("sourceWorkbenchId"),
        "created_at": document.get("createdAt") or "",
        "updated_at": document.get("updatedAt") or "",
        "question_count": len(questions),
        "knowledge_count": len(knowledge),
        "node_count": len(nodes),
        "format_template_id": document.get("formatTemplateId"),
        "current_version": int(document.get("currentVersion") or 1),
        "version_count": len(document.get("versions") or []),
    }


def _version_snapshot(document_id: str, version: int, package: dict[str, Any], created_at: str) -> dict[str, Any]:
    return {
        "version": version,
        "versionId": f"{document_id}-v{version}",
        "createdAt": created_at,
        "title": str(package.get("title") or "未命名讲义"),
        "lessonPackage": deepcopy(package),
    }


def list_saved_handouts(limit: int = 100) -> list[dict[str, Any]]:
    documents = sorted(_read_documents(), key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return [_summary(item) for item in documents[: max(1, min(int(limit or 100), 200))]]


def get_saved_handout(document_id: str) -> dict[str, Any] | None:
    clean_id = str(document_id or "").strip()
    for item in _read_documents():
        if str(item.get("id")) == clean_id:
            result = deepcopy(item)
            result["document_kind"] = "saved_handout"
            return result
    return None


def save_saved_handout(
    lesson_package: dict[str, Any],
    *,
    source_workbench_id: str | None = None,
) -> dict[str, Any]:
    package = deepcopy(lesson_package)
    document_id = str(package.get("id") or uuid4().hex).strip()
    now = datetime.now(UTC).isoformat()
    documents = _read_documents()
    existing = next((item for item in documents if str(item.get("id")) == document_id), None)
    if existing and existing.get("lessonPackage") == package:
        result = deepcopy(existing)
        result["document_kind"] = "saved_handout"
        result["summary"] = _summary(result)
        return result
    current_version = int((existing or {}).get("currentVersion") or 0)
    versions = [item for item in (existing or {}).get("versions", []) if isinstance(item, dict)]
    if existing and not versions and isinstance(existing.get("lessonPackage"), dict):
        versions = [_version_snapshot(document_id, 1, existing["lessonPackage"], str(existing.get("updatedAt") or now))]
        current_version = 1
    current_version += 1 if existing else 0
    if not existing:
        current_version = 1
    versions.append(_version_snapshot(document_id, current_version, package, now))
    versions = versions[-_MAX_VERSIONS:]
    document = {
        "id": document_id,
        "title": str(package.get("title") or "未命名讲义"),
        "subtitle": str(package.get("subtitle") or ""),
        "document_kind": "saved_handout",
        "sourceWorkbenchId": source_workbench_id or (existing or {}).get("sourceWorkbenchId"),
        "createdAt": (existing or {}).get("createdAt") or now,
        "updatedAt": now,
        "formatTemplateId": (existing or {}).get("formatTemplateId"),
        "currentVersion": current_version,
        "versions": versions,
        "lessonPackage": package,
    }
    if existing:
        documents[documents.index(existing)] = document
    else:
        documents.insert(0, document)
    _write_documents(documents)
    return {**document, "summary": _summary(document)}


def list_saved_handout_versions(document_id: str) -> list[dict[str, Any]] | None:
    document = get_saved_handout(document_id)
    if not document:
        return None
    versions = document.get("versions") if isinstance(document.get("versions"), list) else []
    return [
        {
            "version": int(item.get("version") or 0),
            "version_id": str(item.get("versionId") or ""),
            "created_at": item.get("createdAt") or "",
            "title": item.get("title") or "",
            "current": int(item.get("version") or 0) == int(document.get("currentVersion") or 1),
        }
        for item in reversed(versions)
        if isinstance(item, dict)
    ]


def restore_saved_handout_version(document_id: str, version: int) -> dict[str, Any] | None:
    document = get_saved_handout(document_id)
    if not document:
        return None
    versions = document.get("versions") if isinstance(document.get("versions"), list) else []
    target = next((item for item in versions if int(item.get("version") or 0) == int(version)), None)
    package = target.get("lessonPackage") if isinstance(target, dict) else None
    if not isinstance(package, dict):
        raise ValueError(f"讲义版本不存在：{version}")
    restored = save_saved_handout(package, source_workbench_id=document.get("sourceWorkbenchId"))
    restored["restoredFromVersion"] = int(version)
    return restored


def rename_saved_handout(document_id: str, title: str) -> dict[str, Any] | None:
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("讲义名称不能为空")
    documents = _read_documents()
    for index, document in enumerate(documents):
        if str(document.get("id")) != str(document_id):
            continue
        document["title"] = clean_title
        document["updatedAt"] = datetime.now(UTC).isoformat()
        package = document.get("lessonPackage")
        if isinstance(package, dict):
            package["title"] = clean_title
            package["updatedAt"] = document["updatedAt"]
        documents[index] = document
        _write_documents(documents)
        return {**document, "summary": _summary(document)}
    return None


def _update_saved_handout_format_legacy(document_id: str, format_spec: dict[str, Any], template_id: str | None = None) -> dict[str, Any] | None:
    documents = _read_documents()
    for index, document in enumerate(documents):
        if str(document.get("id")) != str(document_id):
            continue
        package = document.get("lessonPackage")
        if not isinstance(package, dict):
            raise ValueError("已保存讲义缺少 lessonPackage")
        package["formatSpec"] = deepcopy(format_spec)
        package["styleConfig"] = deepcopy(format_spec.get("styleConfig") or package.get("styleConfig") or {})
        package["headerFooter"] = deepcopy(format_spec.get("headerFooter") or package.get("headerFooter") or {})
        document["lessonPackage"] = package
        document["formatTemplateId"] = template_id
        document["updatedAt"] = datetime.now(UTC).isoformat()
        documents[index] = document
        _write_documents(documents)
        return {**document, "summary": _summary(document)}
    return None


def update_saved_handout_format(document_id: str, format_spec: dict[str, Any], template_id: str | None = None) -> dict[str, Any] | None:
    """Update formatting through the normal save path so the change is versioned."""
    document = get_saved_handout(document_id)
    if not document:
        return None
    package = document.get("lessonPackage")
    if not isinstance(package, dict):
        raise ValueError("saved handout is missing lessonPackage")
    package["formatSpec"] = deepcopy(format_spec)
    package["styleConfig"] = deepcopy(format_spec.get("styleConfig") or package.get("styleConfig") or {})
    package["headerFooter"] = deepcopy(format_spec.get("headerFooter") or package.get("headerFooter") or {})
    saved = save_saved_handout(package, source_workbench_id=document.get("sourceWorkbenchId"))
    documents = _read_documents()
    for index, current in enumerate(documents):
        if str(current.get("id")) != str(document_id):
            continue
        current["formatTemplateId"] = template_id
        documents[index] = current
        _write_documents(documents)
        saved["formatTemplateId"] = template_id
        saved["summary"] = _summary(current)
        return saved
    return saved
