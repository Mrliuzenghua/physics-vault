from __future__ import annotations

from physics_vault_api.services import lesson_documents


def _package(document_id: str = "lesson-1") -> dict:
    return {
        "id": document_id,
        "title": "讲义",
        "subtitle": "测试",
        "questions": [{"question_id": "q-1"}],
        "knowledgeCards": [],
        "textBlocks": [],
        "nodes": [{"id": "node-1", "type": "question", "questionId": "q-1"}],
    }


def test_saved_handout_is_durable_and_renameable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_documents, "_STORE_FILE", tmp_path / "saved-handouts.json")

    saved = lesson_documents.save_saved_handout(_package(), source_workbench_id="draft-1")
    assert saved["document_kind"] == "saved_handout"
    assert saved["summary"]["source_workbench_id"] == "draft-1"

    renamed = lesson_documents.rename_saved_handout("lesson-1", "新讲义")
    assert renamed and renamed["title"] == "新讲义"
    loaded = lesson_documents.get_saved_handout("lesson-1")
    assert loaded and loaded["lessonPackage"]["title"] == "新讲义"
    assert lesson_documents.list_saved_handouts()[0]["document_kind"] == "saved_handout"


def test_saved_handout_format_updates_package(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_documents, "_STORE_FILE", tmp_path / "saved-handouts.json")
    lesson_documents.save_saved_handout(_package())

    updated = lesson_documents.update_saved_handout_format(
        "lesson-1",
        {"styleConfig": {"fontSize": 12}, "output": {"includeAnswers": True}},
        template_id="teacher_handout",
    )
    assert updated and updated["formatTemplateId"] == "teacher_handout"
    assert updated["lessonPackage"]["formatSpec"]["styleConfig"]["fontSize"] == 12


def test_saved_handout_versions_restore_without_losing_current(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_documents, "_STORE_FILE", tmp_path / "saved-handouts.json")
    lesson_documents.save_saved_handout(_package())
    changed = _package()
    changed["title"] = "第二版"
    lesson_documents.save_saved_handout(changed)

    versions = lesson_documents.list_saved_handout_versions("lesson-1")
    assert versions and len(versions) == 2
    restored = lesson_documents.restore_saved_handout_version("lesson-1", 1)
    assert restored and restored["lessonPackage"]["title"] == "讲义"
    assert lesson_documents.get_saved_handout("lesson-1")["currentVersion"] == 3


def test_repeated_sync_does_not_create_duplicate_versions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_documents, "_STORE_FILE", tmp_path / "saved-handouts.json")
    package = _package()
    lesson_documents.save_saved_handout(package)
    lesson_documents.save_saved_handout(package)
    assert lesson_documents.get_saved_handout("lesson-1")["currentVersion"] == 1
