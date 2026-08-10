from __future__ import annotations

import pytest

from physics_vault_api.services import teaching_projects


def _project(project_id: str = "project-1") -> dict:
    return {
        "id": project_id,
        "title": "牛顿定律复习",
        "projectType": "lesson",
        "contentRevision": 1,
        "content": {
            "meta": {"title": "牛顿定律复习"},
            "nodes": [{"id": "q-node-1", "type": "question", "questionId": "q-1"}],
        },
        "handout": {"id": "handout-1", "status": "draft", "sourceRevision": 1},
        "slides": {"id": "slides-1", "status": "draft", "sourceRevision": 1},
    }


def test_teaching_project_is_durable_and_versioned(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(teaching_projects, "_STORE_FILE", tmp_path / "teaching-projects.json")

    first = teaching_projects.save_teaching_project(_project())
    assert first["document_kind"] == "teaching_project"
    assert first["currentVersion"] == 1
    assert first["summary"]["questionCount"] == 1

    changed = _project()
    changed["contentRevision"] = 2
    changed["content"]["nodes"].append({"id": "text-1", "type": "richText"})
    second = teaching_projects.save_teaching_project(changed, base_updated_at=first["updatedAt"])

    assert second["currentVersion"] == 2
    assert len(second["versions"]) == 2
    loaded = teaching_projects.get_teaching_project("project-1")
    assert loaded and loaded["contentRevision"] == 2


def test_teaching_project_rejects_stale_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(teaching_projects, "_STORE_FILE", tmp_path / "teaching-projects.json")
    first = teaching_projects.save_teaching_project(_project())
    changed = _project()
    changed["title"] = "新标题"
    teaching_projects.save_teaching_project(changed, base_updated_at=first["updatedAt"])

    with pytest.raises(teaching_projects.TeachingProjectConflictError):
        teaching_projects.save_teaching_project(_project(), base_updated_at=first["updatedAt"])


def test_repeated_project_sync_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(teaching_projects, "_STORE_FILE", tmp_path / "teaching-projects.json")
    project = _project()
    first = teaching_projects.save_teaching_project(project)
    repeated = teaching_projects.save_teaching_project(project, base_updated_at=first["updatedAt"])

    assert repeated["currentVersion"] == 1
    assert len(repeated["versions"]) == 1


def test_archive_is_reversible_by_version(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(teaching_projects, "_STORE_FILE", tmp_path / "teaching-projects.json")
    first = teaching_projects.save_teaching_project(_project())
    archived = teaching_projects.archive_teaching_project("project-1", base_updated_at=first["updatedAt"])
    assert archived and archived["status"] == "archived"
    assert archived["currentVersion"] == 2
