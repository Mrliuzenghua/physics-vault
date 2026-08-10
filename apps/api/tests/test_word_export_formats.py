from __future__ import annotations

from physics_vault_api.services import word_export_formats


def test_builtin_template_is_valid() -> None:
    spec = word_export_formats.format_spec_for_template("teacher_handout")
    checked = word_export_formats.validate_format_spec(spec)
    assert checked["ok"] is True
    assert checked["formatSpec"]["output"]["includeAnswers"] is True
    assert checked["formatSpec"]["output"]["includeAnalysis"] is True


def test_custom_template_can_be_saved_and_renamed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(word_export_formats, "_TEMPLATE_FILE", tmp_path / "templates.json")
    result = word_export_formats.save_word_export_template(
        "我的版式",
        word_export_formats.format_spec_for_template("formal_exam", {"styleConfig": {"fontSize": 11}}),
    )
    assert result["ok"] is True
    template_id = result["template"]["id"]

    renamed = word_export_formats.rename_word_export_template(template_id, "重命名版式")
    assert renamed["ok"] is True
    assert renamed["template"]["name"] == "重命名版式"
    assert next(item for item in word_export_formats.list_word_export_templates() if item["id"] == template_id)["name"] == "重命名版式"
