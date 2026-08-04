from pathlib import Path

from physics_vault_api.services.document_pipeline import PandocAdapter
from physics_vault_api.services.question_splitter import ExamQuestionSplitter


def test_markitdown_fallback_binds_docx_images_to_questions(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    source = project_root / "scripts" / "fixtures" / "test_exam_img.docx"
    markdown_path = tmp_path / "document.md"
    media_dir = tmp_path / "media"

    result = PandocAdapter(executable="pandoc-not-installed-for-test").unpack_to_markdown(
        str(source),
        str(markdown_path),
        str(media_dir),
    )

    assert result["image_count"] > 0
    assert "data:image/" not in result["text"]
    assets = [
        {
            "image_id": f"image_{index:04d}",
            "filename": Path(path).name,
            "relative_path": str(path),
        }
        for index, path in enumerate(result["images"], start=1)
    ]
    parsed = ExamQuestionSplitter().split(
        result["text"],
        batch_id="batch-image-test",
        source="image fixture",
        media_assets=assets,
    )
    assert any(question["figures"] for question in parsed["questions"])
