"""File-type routing and stable result shaping for import recognition."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class ImportRecognitionWorkflow:
    """Choose the text or vision path without owning file, task, or MCP state."""

    TEXT_SOURCE_TYPES = frozenset({"doc", "docx", "md", "markdown", "txt", "html"})
    VISION_SOURCE_TYPES = frozenset({"pdf", "jpg", "jpeg", "png", "webp"})

    async def recognize(
        self,
        *,
        batch_id: str,
        source_type: str,
        expected_input_version: int | None,
        run_text_pipeline: Callable[[int | None], dict[str, Any]],
        run_vision_pipeline: Callable[[], Awaitable[Any]],
    ) -> dict[str, Any]:
        source_type = source_type.lower().lstrip(".")
        if source_type in self.TEXT_SOURCE_TYPES:
            return await asyncio.to_thread(run_text_pipeline, expected_input_version)

        if source_type in self.VISION_SOURCE_TYPES:
            task = await run_vision_pipeline()
            return self._vision_response(batch_id, source_type, task)

        return {
            "batch_id": batch_id,
            "status": "failed",
            "pipeline": "word_pandoc_deepseek",
            "source_type": source_type or "unknown",
            "question_count": 0,
            "questions": [],
            "error": f"不支持的文件类型：{source_type or 'unknown'}",
        }

    @staticmethod
    def _vision_response(batch_id: str, source_type: str, task: Any) -> dict[str, Any]:
        task_id = str(getattr(task, "task_id", "") or "")
        error = getattr(task, "error", None)
        if getattr(task, "status", None) == "failed":
            return {
                "task_id": task_id,
                "batch_id": batch_id,
                "status": "failed",
                "pipeline": "vision_qwen_ocr",
                "source_type": source_type,
                "question_count": 0,
                "questions": [],
                "error": error,
                "warnings": [error] if error else [],
            }

        result = getattr(task, "result", None) or {}
        warnings = [str(item) for item in result.get("warnings", []) if str(item).strip()]
        question_count = int(result.get("question_count") or 0)
        response = {
            "task_id": task_id,
            "batch_id": batch_id,
            "status": "completed",
            "pipeline": "vision_qwen_ocr",
            "source_type": source_type,
            "question_count": question_count,
            "questions": result.get("questions") or [],
            "media_assets": result.get("media_assets") or [],
            "markdown_preview": str(result.get("raw_text") or ""),
            "structured_by": "mcp_vl_qwen_ocr",
            "ai_refined_count": 0,
            "warnings": warnings,
        }
        if question_count == 0 and warnings:
            response.update({
                "status": "failed",
                "error": "OCR / 视觉识别未得到题目：" + "；".join(warnings[:3]),
            })
        return response
