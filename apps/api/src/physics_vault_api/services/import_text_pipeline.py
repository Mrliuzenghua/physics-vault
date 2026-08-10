"""Text-import stage collaboration independent of task persistence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CleanedMarkdown:
    """Normalized Markdown ready to be persisted by the import stage."""

    text: str
    media_assets: list[dict[str, Any]]
    warnings: list[str]
    cleaned_by: str


class ImportTextPipeline:
    """Coordinates text cleaning and the three text-import stages through explicit collaborators."""

    def prepare_cleaned_markdown(
        self,
        *,
        markdown_path: Path,
        manifest_path: Path,
        cleaner: Any,
        use_ai: bool,
        ai_cleaner: Callable[[str, list[dict[str, Any]]], dict[str, Any]] | None,
        read_text: Callable[[Path], str],
    ) -> CleanedMarkdown:
        """Read, clean, and optionally refine Markdown before the caller persists it."""
        markdown = read_text(markdown_path)
        media_assets = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
        fallback_result = cleaner.clean_markdown_for_import(markdown, media_assets)
        cleaned_text = str(fallback_result["cleaned_text"])
        warnings = list(fallback_result.get("warnings", []))
        cleaned_by = "local_cleaner"

        if use_ai and ai_cleaner is not None:
            try:
                ai_result = ai_cleaner(markdown, media_assets)
                ai_text = self._normalized_ai_text(ai_result)
                if ai_text:
                    cleaned_text = ai_text
                    cleaned_by = "mcp_llm"
                    ai_warnings = ai_result.get("warnings", [])
                    if isinstance(ai_warnings, list):
                        warnings.extend(str(item) for item in ai_warnings if str(item).strip())
                else:
                    warnings.append("AI 清洗未返回 cleaned_markdown，已使用本地清洗结果。")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"AI 清洗不可用，已使用本地清洗结果：{exc}")

        return CleanedMarkdown(
            text=cleaned_text,
            media_assets=media_assets,
            warnings=warnings,
            cleaned_by=cleaned_by,
        )

    @staticmethod
    def write_cleaned_markdown(
        cleaned_path: Path,
        cleaned_text: str,
        write_text: Callable[[Path, str], None],
    ) -> None:
        """Persist prepared content through the caller's atomic-write primitive."""
        write_text(cleaned_path, cleaned_text)

    def run(
        self,
        *,
        batch_id: str,
        source_type: str,
        expected_input_version: int | None,
        run_pandoc: Callable[[int | None], Any],
        run_clean: Callable[[int | None], Any],
        run_structure: Callable[[int | None], Any],
    ) -> dict[str, Any]:
        """Run the text-stage sequence and return the stable recognition response shape."""
        warnings: list[str] = []

        pandoc_task = run_pandoc(expected_input_version)
        if pandoc_task.status == "failed":
            return self._failed_response(batch_id, source_type, pandoc_task.error)

        clean_task = run_clean(expected_input_version)
        if clean_task.status == "failed":
            warnings.append(clean_task.error or "本地清洗失败，尝试继续结构化")

        structure_task = run_structure(expected_input_version)
        if structure_task.status == "failed":
            return self._failed_response(batch_id, source_type, structure_task.error)

        result = structure_task.result or {}
        pandoc_result = pandoc_task.result or {}
        clean_result = clean_task.result or {}
        warnings.extend(str(item) for item in clean_result.get("warnings", []) if str(item).strip())
        return {
            "task_id": structure_task.task_id,
            "batch_id": batch_id,
            "status": "completed",
            "pipeline": "word_pandoc_local",
            "source_type": source_type,
            "question_count": int(result.get("question_count") or 0),
            "questions": result.get("questions") or [],
            "media_assets": result.get("media_assets") or pandoc_result.get("images") or [],
            "markdown_preview": str(clean_result.get("cleaned_preview") or pandoc_result.get("markdown_preview") or ""),
            "structured_by": str(result.get("structured_by") or ""),
            "ai_refined_count": int(result.get("ai_refined_count") or 0),
            "warnings": warnings,
        }

    @staticmethod
    def _normalized_ai_text(ai_result: dict[str, Any]) -> str:
        ai_text = str(ai_result.get("cleaned_markdown") or ai_result.get("text") or "").strip()
        if ai_text.startswith("{") and "cleaned_markdown" in ai_text:
            try:
                nested = json.loads(ai_text)
                ai_text = str(nested.get("cleaned_markdown") or "").strip() if isinstance(nested, dict) else ""
            except json.JSONDecodeError:
                ai_text = ""
        return ai_text if ai_text and not ai_text.lstrip().startswith("{") else ""

    @staticmethod
    def _failed_response(batch_id: str, source_type: str, error: str | None) -> dict[str, Any]:
        return {
            "batch_id": batch_id,
            "status": "failed",
            "pipeline": "word_pandoc_local",
            "source_type": source_type,
            "question_count": 0,
            "questions": [],
            "error": error,
        }
