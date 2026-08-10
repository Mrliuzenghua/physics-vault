from pathlib import Path
from types import SimpleNamespace

from physics_vault_api.services.import_text_pipeline import ImportTextPipeline


class LocalCleaner:
    def clean_markdown_for_import(self, markdown: str, media_assets: list[dict]) -> dict:
        assert markdown == "raw markdown"
        assert media_assets == [{"filename": "diagram.png"}]
        return {"cleaned_text": "local cleaned", "warnings": ["local warning"]}


def test_prepare_cleaned_markdown_normalizes_nested_ai_response(tmp_path: Path) -> None:
    manifest_path = tmp_path / "media.json"
    manifest_path.write_text('[{"filename": "diagram.png"}]', encoding="utf-8")
    cleaned_path = tmp_path / "cleaned.md"

    pipeline = ImportTextPipeline()
    result = pipeline.prepare_cleaned_markdown(
        markdown_path=tmp_path / "source.md",
        manifest_path=manifest_path,
        cleaner=LocalCleaner(),
        use_ai=True,
        ai_cleaner=lambda _markdown, _assets: {
            "text": '{"cleaned_markdown": "AI cleaned"}',
            "warnings": ["ai warning"],
        },
        read_text=lambda _path: "raw markdown",
    )

    pipeline.write_cleaned_markdown(
        cleaned_path,
        result.text,
        lambda path, text: path.write_text(text, encoding="utf-8"),
    )

    assert cleaned_path.read_text(encoding="utf-8") == "AI cleaned"
    assert result.text == "AI cleaned"
    assert result.cleaned_by == "mcp_llm"
    assert result.warnings == ["local warning", "ai warning"]


def test_run_combines_cleaning_warnings_and_keeps_pandoc_media_fallback() -> None:
    task = lambda **kwargs: SimpleNamespace(**kwargs)
    result = ImportTextPipeline().run(
        batch_id="batch-1",
        source_type="docx",
        expected_input_version=3,
        run_pandoc=lambda version: task(
            status="completed",
            error=None,
            result={"images": [{"filename": "diagram.png"}], "markdown_preview": "pandoc preview"},
            task_id="pandoc-task",
        ),
        run_clean=lambda version: task(
            status="completed",
            error=None,
            result={"cleaned_preview": "clean preview", "warnings": ["clean warning"]},
            task_id="clean-task",
        ),
        run_structure=lambda version: task(
            status="completed",
            error=None,
            result={"question_count": 1, "questions": [{"title": "题目"}], "structured_by": "local"},
            task_id="structure-task",
        ),
    )

    assert result["task_id"] == "structure-task"
    assert result["media_assets"] == [{"filename": "diagram.png"}]
    assert result["markdown_preview"] == "clean preview"
    assert result["warnings"] == ["clean warning"]
