from __future__ import annotations

import pytest

from physics_vault_api.services import lesson_reflections


def _reflection(reflection_id: str = "reflection-1") -> dict:
    return {
        "id": reflection_id,
        "projectId": "project-1",
        "projectTitle": "牛顿定律复习",
        "rating": 3,
        "completed": False,
        "highlights": "互动不错",
        "followUp": "补一道练习",
        "completedFollowUpTaskIds": ["reflection-1-follow-up"],
        "attendedPages": 5,
    }


def test_reflection_is_durable_and_normalized(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_reflections, "_STORE_FILE", tmp_path / "lesson-reflections.json")

    saved = lesson_reflections.save_lesson_reflection(_reflection())
    assert saved["rating"] == 3
    assert saved["attendedPages"] == 5
    assert saved["completedFollowUpTaskIds"] == ["reflection-1-follow-up"]
    loaded = lesson_reflections.get_lesson_reflection("reflection-1")
    assert loaded and loaded["projectId"] == "project-1"
    assert len(lesson_reflections.list_lesson_reflections("project-1")) == 1


def test_reflection_rejects_stale_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_reflections, "_STORE_FILE", tmp_path / "lesson-reflections.json")
    first = lesson_reflections.save_lesson_reflection(_reflection())
    changed = _reflection()
    changed["rating"] = 1
    second = lesson_reflections.save_lesson_reflection(changed, base_updated_at=first["updatedAt"])
    assert second["rating"] == 1

    with pytest.raises(lesson_reflections.LessonReflectionConflictError):
        lesson_reflections.save_lesson_reflection(_reflection(), base_updated_at=first["updatedAt"])


def test_reflection_update_keeps_created_at(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_reflections, "_STORE_FILE", tmp_path / "lesson-reflections.json")
    first = lesson_reflections.save_lesson_reflection(_reflection())
    changed = _reflection()
    changed["completed"] = True
    second = lesson_reflections.save_lesson_reflection(changed, base_updated_at=first["updatedAt"])
    assert second["createdAt"] == first["createdAt"]
    assert second["completed"] is True
