import asyncio
from types import SimpleNamespace

from physics_vault_api.services.import_recognition_workflow import ImportRecognitionWorkflow


def test_text_sources_delegate_to_the_existing_text_pipeline() -> None:
    workflow = ImportRecognitionWorkflow()
    calls: list[int | None] = []

    def run_text_pipeline(expected_input_version: int | None) -> dict[str, object]:
        calls.append(expected_input_version)
        return {"status": "completed", "pipeline": "word_pandoc_deepseek"}

    async def run_vision_pipeline() -> object:
        raise AssertionError("Vision pipeline must not run for text sources")

    result = asyncio.run(
        workflow.recognize(
            batch_id="batch-text",
            source_type=".DOCX",
            expected_input_version=4,
            run_text_pipeline=run_text_pipeline,
            run_vision_pipeline=run_vision_pipeline,
        )
    )

    assert calls == [4]
    assert result == {"status": "completed", "pipeline": "word_pandoc_deepseek"}


def test_failed_vision_task_keeps_the_legacy_failure_shape() -> None:
    workflow = ImportRecognitionWorkflow()

    async def run_vision_pipeline() -> object:
        return SimpleNamespace(task_id="task-vision", status="failed", error="vision unavailable")

    result = asyncio.run(
        workflow.recognize(
            batch_id="batch-vision",
            source_type="pdf",
            expected_input_version=None,
            run_text_pipeline=lambda _version: {},
            run_vision_pipeline=run_vision_pipeline,
        )
    )

    assert result == {
        "task_id": "task-vision",
        "batch_id": "batch-vision",
        "status": "failed",
        "pipeline": "vision_qwen_ocr",
        "source_type": "pdf",
        "question_count": 0,
        "questions": [],
        "error": "vision unavailable",
        "warnings": ["vision unavailable"],
    }


def test_empty_vision_result_with_warnings_is_reported_as_a_failure() -> None:
    workflow = ImportRecognitionWorkflow()

    async def run_vision_pipeline() -> object:
        return SimpleNamespace(
            task_id="task-empty",
            status="completed",
            error=None,
            result={
                "question_count": 0,
                "warnings": ["no usable regions"],
                "media_assets": [{"id": "page-1"}],
            },
        )

    result = asyncio.run(
        workflow.recognize(
            batch_id="batch-empty",
            source_type="png",
            expected_input_version=None,
            run_text_pipeline=lambda _version: {},
            run_vision_pipeline=run_vision_pipeline,
        )
    )

    assert result["status"] == "failed"
    assert result["question_count"] == 0
    assert result["media_assets"] == [{"id": "page-1"}]
    assert result["warnings"] == ["no usable regions"]
    assert "no usable regions" in result["error"]


def test_unsupported_sources_return_a_stable_failure_payload() -> None:
    workflow = ImportRecognitionWorkflow()

    async def run_vision_pipeline() -> object:
        raise AssertionError("Vision pipeline must not run for unsupported sources")

    result = asyncio.run(
        workflow.recognize(
            batch_id="batch-unknown",
            source_type="xlsx",
            expected_input_version=None,
            run_text_pipeline=lambda _version: {},
            run_vision_pipeline=run_vision_pipeline,
        )
    )

    assert result["batch_id"] == "batch-unknown"
    assert result["status"] == "failed"
    assert result["pipeline"] == "word_pandoc_deepseek"
    assert result["source_type"] == "xlsx"
    assert result["question_count"] == 0
