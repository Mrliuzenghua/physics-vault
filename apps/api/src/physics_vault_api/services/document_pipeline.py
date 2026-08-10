from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import shutil
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)

IMPORT_PIPELINE_CONFIG_VERSION = os.getenv("PHYSICS_IMPORT_CONFIG_VERSION", "1").strip() or "1"

from ..paths import default_db_path, default_import_batches_dir, default_review_db_path, project_root
from ..repositories.import_tasks import ImportTask, InMemoryImportTaskRepository
from ..schemas.import_pipeline import (
    AiParseDocumentRequest,
    CleanDocumentRequest,
    ConvertDocumentRequest,
    ParseStructuredQuestionsRequest,
)
from .document_converter import PandocAdapter
from .import_question_parser import (
    StructuredQuestionParsingService,
    extract_generated_questions as _extract_generated_questions,
)
from .import_recognition_workflow import ImportRecognitionWorkflow
from .import_task_coordinator import ImportTaskCoordinator
from .import_text_pipeline import ImportTextPipeline
from .pdf_page_ocr import parse_pdf_by_page
from .import_text_cleaner import ImportTextCleaner
from .import_text_rules import (
    extract_generated_knowledge_drafts as _extract_generated_knowledge_drafts,
    extract_json_payload as _extract_json_payload,
    looks_like_knowledge_review as _looks_like_knowledge_review,
    merge_draft_metadata as _merge_draft_metadata,
    metadata_question_payload as _metadata_question_payload,
    normalize_ai_questions as _normalize_ai_questions,
    normalize_import_question_metadata,
    parse_draft_metadata_result as _parse_draft_metadata_result,
    safe_json_dict as _safe_json_dict,
    source_extension as _source_extension,
)
from .import_batch_storage import (
    ImportBatchStorage,
    StaleBatchVersionError,
    atomic_write_bytes as _atomic_write_bytes,
    atomic_write_json as _atomic_write_json,
    atomic_write_text as _atomic_write_text,
    batch_lock as _batch_lock,
    relative_to_project as _relative_to_project,
    safe_filename as _safe_filename,
    sha256_file as _sha256_file,
)

if TYPE_CHECKING:
    from mcp_contracts.src.contracts import DocumentParser  # type: ignore[import-not-found]
    from .mcp_gateway import McpGatewayService


class DocumentCleaningService:
    """Compatibility facade for import text-cleaning rules."""

    HEADER_PATTERNS = ImportTextCleaner.HEADER_PATTERNS

    def clean(self, payload: CleanDocumentRequest) -> dict[str, str | int]:
        return ImportTextCleaner.clean_text(
            payload.source_text,
            normalize_whitespace=payload.normalize_whitespace,
            strip_headers_footers=payload.strip_headers_footers,
            normalize_math_delimiters=payload.normalize_math_delimiters,
            remove_blank_lines=payload.remove_blank_lines,
        )

    def clean_markdown_for_import(self, markdown: str, media_assets: list[dict]) -> dict:
        return ImportTextCleaner.clean_markdown_for_import(markdown, media_assets)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _document_title(filename: str) -> str:
    """Use the human document title as question provenance, never its suffix."""
    title = Path(str(filename or "")).stem.strip()
    return title or "未命名文档"


def _duplicate_title(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


class ImportPipelineService:
    def __init__(
        self,
        task_repo: InMemoryImportTaskRepository,
        pandoc: PandocAdapter,
        cleaner: DocumentCleaningService,
        parser: StructuredQuestionParsingService,
        document_parser: DocumentParser | None = None,
        mcp_gateway: McpGatewayService | None = None,
    ) -> None:
        self._task_repo = task_repo
        self._pandoc = pandoc
        self._cleaner = cleaner
        self._parser = parser
        self._document_parser = document_parser
        self._mcp_gateway = mcp_gateway
        self._text_pipeline = ImportTextPipeline()
        self._recognition_workflow = ImportRecognitionWorkflow()
        self._batch_storage = ImportBatchStorage()
        self._task_coordinator = ImportTaskCoordinator(
            task_repo=task_repo,
            get_task=self.get_task,
            read_metadata=self._read_batch_metadata,
            write_metadata=self._write_batch_metadata,
            assert_input_version=self._assert_input_version,
            batch_lock=_batch_lock,
            workspace_root=project_root,
            sha256_file=_sha256_file,
            now_iso=_now_iso,
            config_version=IMPORT_PIPELINE_CONFIG_VERSION,
        )

    # Batch-based import pipeline

    def create_batch_from_upload(self, filename: str, content: bytes) -> dict:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        batch_dir = default_import_batches_dir() / batch_id
        source_dir = batch_dir / "source"
        for directory in (source_dir, batch_dir / "pandoc", batch_dir / "ai", batch_dir / "logs"):
            directory.mkdir(parents=True, exist_ok=True)

        stored_filename = _safe_filename(filename)
        source_path = source_dir / stored_filename
        _atomic_write_bytes(source_path, content)

        created_at = _now_iso()
        document_title = _document_title(filename)
        metadata = {
            "batch_id": batch_id,
            "status": "uploaded",
            "original_filename": filename,
            "document_title": document_title,
            "stored_filename": stored_filename,
            "source_path": _relative_to_project(source_path),
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "config_version": IMPORT_PIPELINE_CONFIG_VERSION,
            "content_version": 1,
            "completed_stages": {},
            "created_at": created_at,
            "updated_at": created_at,
            "image_count": 0,
            "question_count": 0,
        }
        self._write_batch_metadata(batch_id, metadata)
        return {
            "batch_id": batch_id,
            "original_filename": filename,
            "document_title": document_title,
            "stored_filename": stored_filename,
            "source_path": str(source_path),
            "relative_source_path": _relative_to_project(source_path),
            "status": "uploaded",
            "created_at": datetime.fromisoformat(created_at),
            "content_version": 1,
        }

    def find_import_batches_by_sha256(self, source_sha256: str) -> list[dict[str, Any]]:
        """Return prior import batches created from the same file content."""
        digest = str(source_sha256 or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            return []
        matches: list[dict[str, Any]] = []
        root = default_import_batches_dir()
        if not root.exists():
            return matches
        for metadata_path in root.glob("batch_*/status.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(metadata.get("source_sha256") or "").lower() != digest:
                continue
            matches.append(
                {
                    "batch_id": str(metadata.get("batch_id") or metadata_path.parent.name),
                    "original_filename": str(metadata.get("original_filename") or ""),
                    "status": str(metadata.get("status") or ""),
                    "created_at": metadata.get("created_at"),
                    "updated_at": metadata.get("updated_at"),
                    "question_count": int(metadata.get("question_count") or 0),
                }
            )
        matches.sort(key=lambda item: (str(item.get("created_at") or ""), item["batch_id"]), reverse=True)
        return matches

    def run_batch_pandoc(
        self,
        batch_id: str,
        *,
        expected_input_version: int | None = None,
    ) -> ImportTask:
        metadata = self._read_batch_metadata(batch_id)
        input_version = expected_input_version or self._content_version(metadata)
        self._assert_input_version(batch_id, input_version)
        cached = self._cached_stage_task(batch_id, "pandoc", input_version)
        if cached is not None:
            return cached
        source_path = project_root() / metadata["source_path"]
        batch_dir = default_import_batches_dir() / batch_id
        markdown_path = batch_dir / "pandoc" / "document.md"
        media_dir = batch_dir / "pandoc" / "media"

        task = self._task_repo.create(
            task_type="pandoc_unpack",
            input_summary={"batch_id": batch_id, "source_path": metadata["source_path"]},
        )
        self._task_repo.mark_running(task.task_id, current_step="pandoc_unpack", progress=5)
        try:
            temp_markdown = markdown_path.with_name(f".{markdown_path.name}.{task.task_id}.tmp")
            temp_media = media_dir.with_name(f".{media_dir.name}.{task.task_id}.tmp")
            result = self._pandoc.unpack_to_markdown(
                source_path=str(source_path),
                markdown_path=str(temp_markdown),
                media_dir=str(temp_media),
            )
            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                _atomic_write_bytes(markdown_path, temp_markdown.read_bytes())
                final_paths: list[str] = []
                for temp_asset in sorted(temp_media.rglob("*")):
                    if temp_asset.is_file():
                        target = media_dir / temp_asset.relative_to(temp_media)
                        _atomic_write_bytes(target, temp_asset.read_bytes())
                        final_paths.append(str(target))
            temp_markdown.unlink(missing_ok=True)
            shutil.rmtree(temp_media, ignore_errors=True)
            images = self._collect_media_assets(final_paths)
            response = {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "pandoc_completed",
                "markdown_path": str(markdown_path),
                "relative_markdown_path": _relative_to_project(markdown_path),
                "media_dir": str(media_dir),
                "relative_media_dir": _relative_to_project(media_dir),
                "image_count": len(images),
                "images": images,
                "markdown_preview": str(result["text"])[:2000],
                "text": result["text"],
                "output_path": str(markdown_path),
            }
            _atomic_write_json(batch_dir / "pandoc" / "media_manifest.json", images)
            metadata.update(
                {
                    "status": "pandoc_completed",
                    "markdown_path": response["relative_markdown_path"],
                    "media_dir": response["relative_media_dir"],
                    "image_count": len(images),
                    "updated_at": _now_iso(),
                }
            )
            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                self._write_batch_metadata(batch_id, metadata)
            completed = self._task_repo.mark_completed(task.task_id, response)
            self._record_stage_checkpoint(batch_id, "pandoc", task.task_id, input_version)
            return completed
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, StaleBatchVersionError):
                metadata.update({"status": "failed", "updated_at": _now_iso(), "error": str(exc)})
                self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_failed(task.task_id, str(exc))
        finally:
            temp_markdown_path = locals().get("temp_markdown")
            if isinstance(temp_markdown_path, Path):
                temp_markdown_path.unlink(missing_ok=True)
            temp_media_path = locals().get("temp_media")
            if isinstance(temp_media_path, Path):
                shutil.rmtree(temp_media_path, ignore_errors=True)

    def extract_batch_images(self, batch_id: str) -> dict:
        """Extract all document images into the batch cache directory.

        This is intentionally narrow in scope: it only prepares a reusable
        media manifest for the frontend image picker and later question
        binding. It does not run OCR or structure questions.
        """
        metadata = self._read_batch_metadata(batch_id)
        ext = _source_extension(metadata)
        batch_dir = default_import_batches_dir() / batch_id
        media_dir = batch_dir / "pandoc" / "media"
        manifest_path = batch_dir / "pandoc" / "media_manifest.json"
        warnings: list[str] = []

        if manifest_path.exists():
            try:
                cached_assets = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(cached_assets, list) and cached_assets:
                    return {
                        "batch_id": batch_id,
                        "status": "cached",
                        "source_type": ext,
                        "image_count": len(cached_assets),
                        "media_dir": str(media_dir),
                        "relative_media_dir": _relative_to_project(media_dir),
                        "media_assets": cached_assets,
                        "warnings": warnings,
                    }
            except json.JSONDecodeError:
                warnings.append("旧的图片清单损坏，已重新提取。")

        if ext in {"doc", "docx", "md", "markdown", "txt", "html"}:
            task = self.run_batch_pandoc(batch_id)
            if task.status == "failed":
                return {
                    "batch_id": batch_id,
                    "status": "failed",
                    "source_type": ext,
                    "image_count": 0,
                    "media_dir": str(media_dir),
                    "relative_media_dir": _relative_to_project(media_dir),
                    "media_assets": [],
                    "warnings": warnings,
                    "error": task.error or "Pandoc 提图失败",
                }
            result = task.result or {}
            return {
                "batch_id": batch_id,
                "status": "completed",
                "source_type": ext,
                "image_count": int(result.get("image_count") or 0),
                "media_dir": str(media_dir),
                "relative_media_dir": _relative_to_project(media_dir),
                "media_assets": result.get("images") or [],
                "warnings": warnings,
            }

        if ext in {"jpg", "jpeg", "png", "webp", "gif", "svg"}:
            source_path = project_root() / metadata["source_path"]
            if not source_path.exists():
                return {
                    "batch_id": batch_id,
                    "status": "failed",
                    "source_type": ext,
                    "image_count": 0,
                    "media_dir": str(media_dir),
                    "relative_media_dir": _relative_to_project(media_dir),
                    "media_assets": [],
                    "warnings": warnings,
                    "error": f"Source file not found: {source_path}",
                }

            media_dir.mkdir(parents=True, exist_ok=True)
            target = media_dir / source_path.name
            if source_path.resolve() != target.resolve():
                shutil.copy2(source_path, target)

            assets = self._collect_media_assets([str(target)])
            _atomic_write_json(manifest_path, assets)
            metadata.update({"image_count": len(assets), "updated_at": _now_iso()})
            self._write_batch_metadata(batch_id, metadata)
            return {
                "batch_id": batch_id,
                "status": "completed",
                "source_type": ext,
                "image_count": len(assets),
                "media_dir": str(media_dir),
                "relative_media_dir": _relative_to_project(media_dir),
                "media_assets": assets,
                "warnings": warnings,
            }

        if ext == "pdf":
            return {
                "batch_id": batch_id,
                "status": "completed",
                "source_type": ext,
                "image_count": 0,
                "media_dir": str(media_dir),
                "relative_media_dir": _relative_to_project(media_dir),
                "media_assets": [],
                "warnings": ["PDF 提取配图当前仅缓存 OCR 页面图，不直接抽取内嵌插图。建议走智能识别管线。"],
            }

        return {
            "batch_id": batch_id,
            "status": "failed",
            "source_type": ext,
            "image_count": 0,
            "media_dir": str(media_dir),
            "relative_media_dir": _relative_to_project(media_dir),
            "media_assets": [],
            "warnings": warnings,
            "error": f"Unsupported source type for image extraction: {ext or 'unknown'}",
        }

    def _run_text_pipeline(
        self,
        batch_id: str,
        ext: str,
        expected_input_version: int | None = None,
    ) -> dict:
        """Synchronous text-document pipeline (run in a thread by recognize_batch)."""
        return self._text_pipeline.run(
            batch_id=batch_id,
            source_type=ext,
            expected_input_version=expected_input_version,
            run_pandoc=lambda version: self.run_batch_pandoc(batch_id, expected_input_version=version),
            run_clean=lambda version: self.run_batch_ai_clean(
                batch_id,
                use_ai=False,
                expected_input_version=version,
            ),
            run_structure=lambda version: self.structure_batch_questions(
                batch_id,
                use_ai_refine=False,
                expected_input_version=version,
            ),
        )

    async def recognize_batch(
        self,
        batch_id: str,
        *,
        expected_input_version: int | None = None,
    ) -> dict:
        """Compatibility entry point for text/vision recognition orchestration."""
        metadata = self._read_batch_metadata(batch_id)
        ext = _source_extension(metadata)

        async def run_vision_pipeline() -> ImportTask:
            latest_metadata = self._read_batch_metadata(batch_id)
            source_path = project_root() / latest_metadata["source_path"]
            return await self.ai_parse_document(
                AiParseDocumentRequest(
                    batch_id=batch_id,
                    file_path=str(source_path),
                    file_type=ext,  # type: ignore[arg-type]
                    mode="image_document" if ext != "pdf" else "auto",
                    enable_preprocess=True,
                    enable_region_detection=True,
                    enable_figure_extraction=True,
                    enable_table_extraction=True,
                    ignore_headers_footers=True,
                )
            )

        return await self._recognition_workflow.recognize(
            batch_id=batch_id,
            source_type=ext,
            expected_input_version=expected_input_version,
            run_text_pipeline=lambda version: self._run_text_pipeline(batch_id, ext, version),
            run_vision_pipeline=run_vision_pipeline,
        )

    def run_batch_ai_clean(
        self,
        batch_id: str,
        use_ai: bool = True,
        *,
        expected_input_version: int | None = None,
    ) -> ImportTask:
        metadata = self._read_batch_metadata(batch_id)
        input_version = expected_input_version or self._content_version(metadata)
        self._assert_input_version(batch_id, input_version)
        cached = self._cached_stage_task(batch_id, "ai_clean", input_version)
        if cached is not None:
            return cached
        batch_dir = default_import_batches_dir() / batch_id
        markdown_path = project_root() / metadata["markdown_path"]
        manifest_path = batch_dir / "pandoc" / "media_manifest.json"
        cleaned_path = batch_dir / "ai" / "cleaned.md"

        task = self._task_repo.create(
            task_type="ai_clean_markdown",
            input_summary={"batch_id": batch_id, "markdown_path": metadata.get("markdown_path")},
        )
        self._task_repo.mark_running(task.task_id, current_step="ai_clean", progress=5)
        try:
            cleaned = self._text_pipeline.prepare_cleaned_markdown(
                markdown_path=markdown_path,
                manifest_path=manifest_path,
                cleaner=self._cleaner,
                use_ai=use_ai,
                ai_cleaner=(
                    self._mcp_gateway.clean_import_markdown
                    if self._mcp_gateway is not None
                    else None
                ),
                read_text=PandocAdapter._read_output_text,
            )
            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                self._text_pipeline.write_cleaned_markdown(
                    cleaned_path,
                    cleaned.text,
                    _atomic_write_text,
                )
            response = {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "ai_clean_completed",
                "cleaned_markdown_path": str(cleaned_path),
                "relative_cleaned_markdown_path": _relative_to_project(cleaned_path),
                "cleaned_preview": cleaned.text[:2000],
                "text": cleaned.text,
                "cleaned_by": cleaned.cleaned_by,
                "warnings": cleaned.warnings,
            }
            metadata.update(
                {
                    "status": "ai_clean_completed",
                    "cleaned_markdown_path": response["relative_cleaned_markdown_path"],
                    "updated_at": _now_iso(),
                }
            )
            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                self._write_batch_metadata(batch_id, metadata)
            completed = self._task_repo.mark_completed(task.task_id, response)
            self._record_stage_checkpoint(batch_id, "ai_clean", task.task_id, input_version)
            return completed
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, StaleBatchVersionError):
                metadata.update({"status": "failed", "updated_at": _now_iso(), "error": str(exc)})
                self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_failed(task.task_id, str(exc))

    def structure_batch_questions(
        self,
        batch_id: str,
        use_ai_refine: bool = True,
        *,
        expected_input_version: int | None = None,
    ) -> ImportTask:
        metadata = self._read_batch_metadata(batch_id)
        input_version = expected_input_version or self._content_version(metadata)
        self._assert_input_version(batch_id, input_version)
        cached = self._cached_stage_task(batch_id, "ai_structure", input_version)
        if cached is not None:
            return cached
        batch_dir = default_import_batches_dir() / batch_id
        markdown_key = metadata.get("cleaned_markdown_path") or metadata["markdown_path"]
        markdown_path = project_root() / markdown_key
        manifest_path = batch_dir / "pandoc" / "media_manifest.json"
        raw_json_path = batch_dir / "ai" / "questions.raw.json"
        normalized_json_path = batch_dir / "ai" / "questions.normalized.json"

        task = self._task_repo.create(
            task_type="ai_structure_questions",
            input_summary={"batch_id": batch_id, "markdown_path": metadata.get("markdown_path")},
        )
        self._task_repo.mark_running(task.task_id, current_step="structure_questions", progress=5)
        try:
            markdown = PandocAdapter._read_output_text(markdown_path)
            media_assets = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
            result = self._parser.parse_markdown_with_images(
                markdown=markdown,
                batch_id=batch_id,
                source=str(
                    metadata.get("document_title")
                    or _document_title(str(metadata.get("original_filename") or ""))
                ),
                media_assets=media_assets,
            )
            questions = result["questions"]
            structured_by = "local_markdown_parser"
            ai_refined_count = 0

            # ── AI refinement pass (manual/import routes can opt in) ──
            if use_ai_refine and self._mcp_gateway is not None and questions:
                try:
                    ai_result = self._mcp_gateway.refine_import_questions(questions)
                    ai_questions = ai_result.get("questions")
                    if isinstance(ai_questions, list) and len(ai_questions) == len(questions):
                        questions = ai_questions
                        ai_refined_count = int(ai_result.get("refined_count", 0))
                        if ai_refined_count > 0:
                            structured_by = "local_parser+mcp_llm"
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AI question refinement unavailable, keeping local parse: %s", exc)

            questions = [
                normalize_import_question_metadata(question)
                for question in questions
                if isinstance(question, dict)
            ]

            response = {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "ai_completed",
                "question_count": len(questions),
                "source": str(metadata.get("document_title") or "未命名文档"),
                "questions": questions,
                "raw_json_path": str(raw_json_path),
                "normalized_json_path": str(normalized_json_path),
                "structured_by": structured_by,
                "ai_refined_count": ai_refined_count,
                "media_assets": media_assets,
            }
            duplicates = self._find_duplicate_titles(questions, batch_id=batch_id)
            response["duplicate_candidates"] = duplicates
            metadata["duplicate_count"] = len(duplicates)
            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                _atomic_write_json(raw_json_path, response)
                _atomic_write_json(normalized_json_path, questions)
            metadata.update(
                {
                    "status": "ai_completed",
                    "question_count": len(questions),
                    "raw_json_path": _relative_to_project(raw_json_path),
                    "normalized_json_path": _relative_to_project(normalized_json_path),
                    "updated_at": _now_iso(),
                }
            )
            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                self._write_batch_metadata(batch_id, metadata)
            completed = self._task_repo.mark_completed(task.task_id, response)
            self._record_stage_checkpoint(batch_id, "ai_structure", task.task_id, input_version)
            return completed
        except Exception as exc:  # noqa: BLE001
            if not isinstance(exc, StaleBatchVersionError):
                metadata.update({"status": "failed", "updated_at": _now_iso(), "error": str(exc)})
                self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_failed(task.task_id, str(exc))

    def refine_batch_questions(self, batch_id: str, questions: list[dict]) -> dict:
        """Second-pass AI proofreading of questions on the review page.

        Reuses ``mcp_gateway.refine_import_questions`` to correct titles,
        options, answers and analysis. Falls back to the input when AI is
        unavailable so the caller always receives a usable question list.
        """
        warnings: list[str] = []
        refined_by = "local_only"
        refined_count = 0

        if not questions:
            return {
                "batch_id": batch_id,
                "status": "ok",
                "refined_count": 0,
                "questions": [],
                "refined_by": refined_by,
                "warnings": warnings,
            }

        if self._mcp_gateway is None:
            warnings.append("AI 校对不可用，未配置 MCP 服务")
            return {
                "batch_id": batch_id,
                "status": "ok",
                "refined_count": 0,
                "questions": questions,
                "refined_by": refined_by,
                "warnings": warnings,
            }

        try:
            ai_result = self._mcp_gateway.refine_import_questions(questions)
            ai_questions = ai_result.get("questions")
            if isinstance(ai_questions, list) and len(ai_questions) == len(questions):
                refined_count = int(ai_result.get("refined_count", 0))
                refined_by = "mcp_llm" if refined_count > 0 else "mcp_llm_no_change"
                questions = ai_questions
            else:
                warnings.append("AI 返回数量与输入不一致，已保留原题")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"AI 校对失败：{exc}")

        return {
            "batch_id": batch_id,
            "status": "ok",
            "refined_count": refined_count,
            "questions": questions,
            "refined_by": refined_by,
            "warnings": warnings,
        }

    async def complete_draft_metadata(
        self,
        batch_id: str,
        questions: list[dict],
        fields: list[str],
        force_overwrite: bool = False,
    ) -> dict:
        """AI-fill metadata for import drafts before they are saved to the bank."""

        allowed_fields = [field for field in fields if field in {"knowledge_points", "tags", "source"}]
        warnings: list[str] = []
        if not questions:
            return {
                "batch_id": batch_id,
                "status": "ok",
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "questions": [],
                "warnings": warnings,
            }
        if not allowed_fields:
            warnings.append("No supported metadata fields requested")
            return {
                "batch_id": batch_id,
                "status": "ok",
                "updated": 0,
                "skipped": len(questions),
                "failed": 0,
                "questions": questions,
                "warnings": warnings,
            }
        if self._mcp_gateway is None:
            warnings.append("AI metadata service is not configured")
            return {
                "batch_id": batch_id,
                "status": "ok",
                "updated": 0,
                "skipped": len(questions),
                "failed": 0,
                "questions": questions,
                "warnings": warnings,
            }

        try:
            raw = await self._mcp_gateway.generate_metadata({
                "items": [
                    {
                        "question_id": str(question.get("question_id") or f"{batch_id}_q{index:04d}"),
                        "question": _metadata_question_payload(question),
                    }
                    for index, question in enumerate(questions, start=1)
                ],
                "fields": allowed_fields,
                "constraints": {},
                "only_fill_empty": not force_overwrite,
                "strict_enum_match": False,
            })
            generated = _parse_draft_metadata_result(raw)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"AI metadata generation failed: {exc}")
            return {
                "batch_id": batch_id,
                "status": "ok",
                "updated": 0,
                "skipped": 0,
                "failed": len(questions),
                "questions": questions,
                "warnings": warnings,
            }

        updated_questions: list[dict] = []
        updated = 0
        skipped = 0
        for question in questions:
            qid = str(question.get("question_id") or "")
            patch = generated.get(qid, {})
            merged, changed = _merge_draft_metadata(question, patch, allowed_fields, force_overwrite)
            updated_questions.append(merged)
            if changed:
                updated += 1
            else:
                skipped += 1

        return {
            "batch_id": batch_id,
            "status": "ok",
            "updated": updated,
            "skipped": skipped,
            "failed": 0,
            "questions": updated_questions,
            "warnings": warnings,
        }

    def get_batch_status(self, batch_id: str) -> dict:
        return self._read_batch_metadata(batch_id)

    def list_batch_overview(self, limit: int = 80) -> list[dict[str, Any]]:
        """List persisted import batches so progress survives a page refresh."""
        limit = min(max(int(limit or 80), 1), 200)
        root = default_import_batches_dir()
        if not root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for status_path in root.glob("batch_*/status.json"):
            try:
                metadata = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.append({
                "batch_id": str(metadata.get("batch_id") or status_path.parent.name),
                "source": str(metadata.get("document_title") or _document_title(str(metadata.get("original_filename") or ""))),
                "original_filename": str(metadata.get("original_filename") or ""),
                "status": str(metadata.get("status") or "unknown"),
                "question_count": int(metadata.get("question_count") or 0),
                "image_count": int(metadata.get("image_count") or 0),
                "duplicate_count": int(metadata.get("duplicate_count") or 0),
                "updated_at": str(metadata.get("updated_at") or ""),
                "created_at": str(metadata.get("created_at") or ""),
                "error": str(metadata.get("error") or "") or None,
                "retryable": str(metadata.get("status") or "") == "failed",
                "active_task_id": str(metadata.get("active_task_id") or "") or None,
                "active_operation": str(metadata.get("active_operation") or "") or None,
                "content_version": self._content_version(metadata),
            })
        return sorted(rows, key=lambda item: (item["updated_at"], item["batch_id"]), reverse=True)[:limit]

    def retry_batch(self, batch_id: str, *, use_ai_cleanup: bool = True) -> dict[str, Any]:
        """Retry a saved Word/text batch without uploading the file again."""
        metadata = self._read_batch_metadata(batch_id)
        source_path = project_root() / str(metadata.get("source_path") or "")
        if not source_path.exists():
            raise HTTPException(status_code=404, detail="Original import file is missing; upload it again.")
        if _source_extension(metadata) not in {"doc", "docx", "md", "markdown", "txt", "html"}:
            raise HTTPException(status_code=400, detail="Only Word/text batches can be retried here.")
        for task in (
            self.run_batch_pandoc(batch_id),
            self.run_batch_ai_clean(batch_id, use_ai=use_ai_cleanup),
            self.structure_batch_questions(batch_id, use_ai_refine=use_ai_cleanup),
        ):
            if task.status == "failed":
                raise HTTPException(status_code=400, detail=task.error or "Batch retry failed")
        return task.result or {"batch_id": batch_id, "status": "completed"}

    def confirm_batch_questions(
        self,
        batch_id: str,
        questions: list[dict],
        *,
        media_assets: list[dict] | None = None,
        expected_input_version: int | None = None,
    ) -> ImportTask:
        """Persist user-edited questions and expose them as a completed task.

        The review workbench loads import tasks by id, so wrapping the edited
        list in a completed task lets the existing /review/{taskId} flow pick
        it up without any changes.
        """
        metadata = self._read_batch_metadata(batch_id)
        questions = [normalize_import_question_metadata(dict(question)) for question in questions]
        current_version = self._content_version(metadata)
        if expected_input_version is not None and expected_input_version != current_version:
            raise HTTPException(
                status_code=409,
                detail="The import draft changed after it was loaded; refresh before saving.",
            )
        batch_dir = default_import_batches_dir() / batch_id
        edited_path = batch_dir / "ai" / "questions.edited.json"
        edited_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_media_assets = [dict(asset) for asset in (media_assets or []) if isinstance(asset, dict)]
        if not resolved_media_assets:
            resolved_media_assets = self.list_batch_images(batch_id)
        if resolved_media_assets:
            _atomic_write_json(batch_dir / "pandoc" / "media_manifest.json", resolved_media_assets)

        # Regenerate stable question ids in order (user may have deleted/merged)
        for index, q in enumerate(questions, start=1):
            q["question_id"] = f"{batch_id}_q{index:04d}"
            q["import_batch_id"] = batch_id

        snapshot_hash = hashlib.sha256(
            json.dumps(
                {"questions": questions, "media_assets": resolved_media_assets},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        confirmation_key = hashlib.sha256(
            f"confirm:{batch_id}:{snapshot_hash}:{IMPORT_PIPELINE_CONFIG_VERSION}".encode("utf-8")
        ).hexdigest()
        create_or_get = getattr(self._task_repo, "create_or_get", None)
        summary = {
            "batch_id": batch_id,
            "question_count": len(questions),
            "source": str(metadata.get("document_title") or "Untitled document"),
            "input_version": current_version,
            "snapshot_sha256": snapshot_hash,
        }
        if callable(create_or_get):
            task, created = create_or_get(
                task_type="import_confirmed",
                input_summary=summary,
                idempotency_key=confirmation_key,
            )
            if not created:
                return task
        else:
            task = self._task_repo.create(
                task_type="import_confirmed",
                input_summary=summary,
                idempotency_key=confirmation_key,
            )
            created = True

        with _batch_lock(batch_id):
            latest = self._read_batch_metadata(batch_id)
            if self._content_version(latest) != current_version:
                if created:
                    delete_task = getattr(self._task_repo, "delete", None)
                    if callable(delete_task):
                        delete_task(task.task_id)
                raise HTTPException(
                    status_code=409,
                    detail="The import draft changed while it was being saved; refresh and retry.",
                )
            _atomic_write_json(edited_path, questions)
            metadata = latest
            metadata.update(
                {
                    "status": "confirmed",
                    "question_count": len(questions),
                    "image_count": len(resolved_media_assets),
                    "edited_json_path": _relative_to_project(edited_path),
                    "content_version": current_version + 1,
                    "updated_at": _now_iso(),
                }
            )
            _atomic_write_json(self._batch_metadata_path(batch_id), metadata)

        self._task_repo.mark_running(task.task_id, current_step="save_review_snapshot", progress=10)
        result = {
            "task_id": task.task_id,
            "batch_id": batch_id,
            "status": "confirmed",
            "question_count": len(questions),
            "source": str(metadata.get("document_title") or "未命名文档"),
            "questions": questions,
            "media_assets": resolved_media_assets,
            "edited_json_path": str(edited_path),
        }
        return self._task_repo.mark_completed(task.task_id, result)

    def create_ai_generated_review_task(
        self,
        source_text: str,
        source: str = "AI 题库助手",
        chat_context: str | None = None,
        session_id: str | None = None,
    ) -> ImportTask:
        """Expose AI-generated content as a completed review workbench task."""
        batch_id = f"ai_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        knowledge_drafts: list[dict] = []
        if _looks_like_knowledge_review(source_text):
            knowledge_drafts, warnings = _extract_generated_knowledge_drafts(source_text, batch_id)
            questions: list[dict] = []
        else:
            questions, warnings = _extract_generated_questions(source_text, batch_id, source)
            questions = [normalize_import_question_metadata(question) for question in questions]
        if not questions and not knowledge_drafts:
            raise HTTPException(status_code=400, detail=warnings[0] if warnings else "没有识别到可送审的试题")

        batch_dir = default_import_batches_dir() / batch_id
        ai_dir = batch_dir / "ai"
        ai_dir.mkdir(parents=True, exist_ok=True)
        (ai_dir / "source.md").write_text(source_text, encoding="utf-8")
        (ai_dir / "questions.generated.json").write_text(
            json.dumps(questions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if knowledge_drafts:
            (ai_dir / "knowledge.generated.json").write_text(
                json.dumps(knowledge_drafts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if chat_context:
            (ai_dir / "chat_context.md").write_text(chat_context, encoding="utf-8")

        metadata = {
            "batch_id": batch_id,
            "status": "ai_review",
            "original_filename": "AI生成内容",
            "source_path": _relative_to_project(ai_dir / "source.md"),
            "question_count": len(questions),
            "knowledge_count": len(knowledge_drafts),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "session_id": session_id,
        }
        self._write_batch_metadata(batch_id, metadata)

        task = self._task_repo.create(
            task_type="ai_generated_knowledge_review" if knowledge_drafts and not questions else "ai_generated_review",
            input_summary={
                "batch_id": batch_id,
                "question_count": len(questions),
                "knowledge_count": len(knowledge_drafts),
            },
        )
        self._task_repo.mark_running(task.task_id, current_step="prepare_ai_review", progress=10)
        result = {
            "task_id": task.task_id,
            "batch_id": batch_id,
            "status": "ai_review",
            "source": source,
            "question_count": len(questions),
            "knowledge_count": len(knowledge_drafts),
            "questions": questions,
            "knowledge_drafts": knowledge_drafts,
            "media_assets": [],
            "warnings": warnings,
            "source_text_path": str(ai_dir / "source.md"),
            "chat_context_path": str(ai_dir / "chat_context.md") if chat_context else None,
            "session_id": session_id,
        }
        return self._task_repo.mark_completed(task.task_id, result)

    def add_batch_image(self, batch_id: str, filename: str, content: bytes) -> dict:
        """Store an extra image into the batch media dir and update the manifest."""
        self._read_batch_metadata(batch_id)  # 404 guard
        batch_dir = default_import_batches_dir() / batch_id
        media_dir = batch_dir / "pandoc" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        safe = _safe_filename(filename)
        stem = Path(safe).stem or "image"
        suffix = Path(safe).suffix.lower() or ".png"
        stored_name = f"{stem}-{uuid4().hex[:6]}{suffix}"
        target = media_dir / stored_name
        _atomic_write_bytes(target, content)

        manifest_path = batch_dir / "pandoc" / "media_manifest.json"
        manifest: list[dict] = []
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = []
        asset = {
            "image_id": f"image_{len(manifest) + 1:04d}",
            "filename": stored_name,
            "relative_path": _relative_to_project(target),
            "absolute_path": str(target),
            "size": len(content),
        }
        manifest.append(asset)
        _atomic_write_json(manifest_path, manifest)
        metadata = self._read_batch_metadata(batch_id)
        metadata.update({"image_count": len(manifest), "updated_at": _now_iso()})
        self._write_batch_metadata(batch_id, metadata)
        return asset

    def list_batch_images(self, batch_id: str) -> list[dict]:
        """Read the persisted batch image manifest used by the review cache."""
        self._read_batch_metadata(batch_id)  # 404 guard
        manifest_path = default_import_batches_dir() / batch_id / "pandoc" / "media_manifest.json"
        if not manifest_path.exists():
            return []
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [dict(asset) for asset in manifest if isinstance(asset, dict)] if isinstance(manifest, list) else []

    def _batch_metadata_path(self, batch_id: str) -> Path:
        return self._batch_storage.metadata_path(batch_id)

    def _find_duplicate_titles(self, questions: list[dict], *, batch_id: str) -> list[dict[str, Any]]:
        """Flag exact normalized title matches in the canonical DB and review drafts."""
        wanted = {
            _duplicate_title(str(question.get("title") or "")): index
            for index, question in enumerate(questions, start=1)
            if _duplicate_title(str(question.get("title") or ""))
        }
        if not wanted:
            return []
        results: list[dict[str, Any]] = []
        with sqlite3.connect(default_db_path()) as conn:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(questions)").fetchall()}
            title_col = "stem_text" if "stem_text" in columns else "title" if "title" in columns else None
            if title_col:
                for question_id, title in conn.execute(f"SELECT question_id, {title_col} FROM questions"):
                    key = _duplicate_title(str(title or ""))
                    if key in wanted:
                        results.append({"question_index": wanted[key], "scope": "canonical", "question_id": question_id, "title": str(title or "")[:120]})
        with sqlite3.connect(default_review_db_path()) as conn:
            for task_id, raw in conn.execute("SELECT task_id, result_json FROM import_pipeline_tasks WHERE task_type = 'import_confirmed'"):
                try:
                    payload = json.loads(raw or "{}")
                except json.JSONDecodeError:
                    continue
                for question in payload.get("questions") or []:
                    if not isinstance(question, dict) or str(question.get("import_batch_id") or "") == batch_id:
                        continue
                    key = _duplicate_title(str(question.get("title") or ""))
                    if key in wanted:
                        results.append({"question_index": wanted[key], "scope": "review_workspace", "task_id": task_id, "question_id": question.get("question_id"), "title": str(question.get("title") or "")[:120]})
        return results

    def _read_batch_metadata(self, batch_id: str) -> dict:
        return self._batch_storage.read_metadata(batch_id)

    def _write_batch_metadata(self, batch_id: str, metadata: dict) -> None:
        self._batch_storage.write_metadata(batch_id, metadata)

    def _content_version(self, metadata: dict[str, Any]) -> int:
        return self._batch_storage.content_version(metadata)

    def _assert_input_version(self, batch_id: str, expected_version: int) -> dict[str, Any]:
        return self._batch_storage.assert_input_version(batch_id, expected_version)

    def _idempotency_key(self, operation: str, batch_id: str, metadata: dict[str, Any]) -> str:
        return self._task_coordinator.idempotency_key(operation, batch_id, metadata)

    def _result_is_valid(self, operation: str, task: ImportTask) -> bool:
        return self._task_coordinator.result_is_valid(operation, task)

    def _record_stage_checkpoint(
        self,
        batch_id: str,
        stage: str,
        task_id: str,
        input_version: int,
    ) -> None:
        self._task_coordinator.record_stage_checkpoint(batch_id, stage, task_id, input_version)

    def _cached_stage_task(self, batch_id: str, stage: str, input_version: int) -> ImportTask | None:
        return self._task_coordinator.cached_stage_task(batch_id, stage, input_version)

    @staticmethod
    def _collect_media_assets(paths: list[str]) -> list[dict]:
        assets = []
        for index, raw_path in enumerate(paths, start=1):
            path = Path(raw_path)
            assets.append(
                {
                    "image_id": f"image_{index:04d}",
                    "filename": path.name,
                    "relative_path": _relative_to_project(path),
                    "absolute_path": str(path),
                    "size": path.stat().st_size if path.exists() else 0,
                }
            )
        return assets

    # ── Existing sync methods (unchanged) ──

    def create_background_batch_task(
        self,
        operation: str,
        batch_id: str,
        *,
        max_attempts: int = 1,
    ) -> ImportTask:
        task, _ = self.prepare_background_batch_task(operation, batch_id, max_attempts=max_attempts)
        return task

    def prepare_background_batch_task(
        self,
        operation: str,
        batch_id: str,
        *,
        max_attempts: int = 1,
        request_context: dict[str, Any] | None = None,
    ) -> tuple[ImportTask, bool]:
        return self._task_coordinator.prepare_background_task(
            operation,
            batch_id,
            max_attempts=max_attempts,
            request_context=request_context,
        )

    def execute_background_batch_task(
        self,
        task_id: str,
        operation: str,
        batch_id: str,
    ) -> ImportTask:
        return self._task_coordinator.execute_background_task(
            task_id,
            operation,
            batch_id,
            self._run_background_batch_operation,
        )

    def _run_background_batch_operation(
        self,
        operation: str,
        batch_id: str,
        expected_input_version: int,
    ) -> dict[str, Any]:
        """Run a domain stage after the coordinator has claimed its persisted task."""
        import asyncio

        if operation == "recognize":
            result = asyncio.run(
                self.recognize_batch(batch_id, expected_input_version=expected_input_version)
            )
            if result.get("status") == "failed":
                raise RuntimeError(str(result.get("error") or "Import recognition failed"))
        else:
            runners = {
                "pandoc": lambda: self.run_batch_pandoc(
                    batch_id, expected_input_version=expected_input_version
                ),
                "ai_clean": lambda: self.run_batch_ai_clean(
                    batch_id, use_ai=True, expected_input_version=expected_input_version
                ),
                "ai_structure": lambda: self.structure_batch_questions(
                    batch_id, use_ai_refine=True, expected_input_version=expected_input_version
                ),
            }
            runner = runners.get(operation)
            if runner is None:
                raise ValueError(f"Unsupported background import operation: {operation}")
            child_task = runner()
            if child_task.status == "failed":
                raise RuntimeError(child_task.error or f"Import operation failed: {operation}")
            result = dict(child_task.result or {})
        return result

    def mark_background_task_retrying(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
    ) -> ImportTask:
        return self._task_coordinator.mark_background_task_retrying(
            task_id,
            error,
            error_type=error_type,
            user_message=user_message,
            technical_details=technical_details,
        )

    def fail_background_task(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
        retryable: bool = False,
    ) -> ImportTask:
        return self._task_coordinator.fail_background_task(
            task_id,
            error,
            error_type=error_type,
            user_message=user_message,
            technical_details=technical_details,
            retryable=retryable,
        )

    def convert_document(self, payload: ConvertDocumentRequest) -> ImportTask:
        task = self._task_repo.create(
            task_type="convert_document",
            input_summary={
                "source_path": payload.source_path,
                "source_type": payload.source_type,
                "target_format": payload.target_format,
            },
        )
        self._task_repo.mark_running(task.task_id, current_step="convert_document", progress=5)
        try:
            result = self._pandoc.convert(
                source_path=payload.source_path,
                target_format=payload.target_format,
                output_path=payload.output_path,
            )
            return self._task_repo.mark_completed(task.task_id, result)
        except Exception as exc:  # noqa: BLE001
            return self._task_repo.mark_failed(task.task_id, str(exc))

    def clean_document(self, payload: CleanDocumentRequest) -> ImportTask:
        task = self._task_repo.create(
            task_type="clean_document",
            input_summary={"source_length": len(payload.source_text)},
        )
        self._task_repo.mark_running(task.task_id, current_step="clean_document", progress=5)
        try:
            result = self._cleaner.clean(payload)
            return self._task_repo.mark_completed(task.task_id, result)
        except Exception as exc:  # noqa: BLE001
            return self._task_repo.mark_failed(task.task_id, str(exc))

    def parse_structured_questions(self, payload: ParseStructuredQuestionsRequest) -> ImportTask:
        task = self._task_repo.create(
            task_type="parse_structured_questions",
            input_summary={
                "import_batch_id": payload.import_batch_id,
                "source_path": payload.source_path,
            },
        )
        self._task_repo.mark_running(task.task_id, current_step="parse_questions", progress=5)
        try:
            result = self._parser.parse(payload)
            return self._task_repo.mark_completed(task.task_id, result)
        except Exception as exc:  # noqa: BLE001
            return self._task_repo.mark_failed(task.task_id, str(exc))

    # ── MCP-backed async methods ──

    async def ai_parse_document(self, payload: AiParseDocumentRequest) -> ImportTask:
        """Use MCP-VL DocumentParser for AI-based image/PDF/scan parsing.

        Falls back to a clear error when the MCP provider is not configured
        (mode=disabled or no DocumentParser injected).
        """
        task = self._task_repo.create(
            task_type="ai_parse_document",
            input_summary={
                "file_path": payload.file_path,
                "file_type": payload.file_type,
                "batch_id": payload.batch_id,
            },
        )
        self._task_repo.mark_running(task.task_id, current_step="ai_parse_document", progress=5)

        if self._mcp_gateway is None and self._document_parser is None:
            return self._task_repo.mark_failed(
                task.task_id,
                "MCP 文档解析未配置：AI 服务未启用或当前处于离线模式",
            )

        from ..bootstrap import configure_workspace_imports
        configure_workspace_imports()
        from mcp_contracts.src.errors import AppError  # type: ignore[import-not-found]
        from mcp_contracts.src.models import ParseDocumentInput  # type: ignore[import-not-found]

        try:
            mcp_input = ParseDocumentInput(
                batch_id=payload.batch_id,
                file_path=payload.file_path,
                file_type=payload.file_type,
                mode=payload.mode,
                enable_preprocess=payload.enable_preprocess,
                enable_region_detection=payload.enable_region_detection,
                enable_figure_extraction=payload.enable_figure_extraction,
                enable_table_extraction=payload.enable_table_extraction,
                formula_format=payload.formula_format,
                ignore_headers_footers=payload.ignore_headers_footers,
            )
            if self._mcp_gateway is not None:
                source_path = Path(payload.file_path)
                if payload.file_type == "pdf" and source_path.exists():
                    parsed = await parse_pdf_by_page(
                        gateway=self._mcp_gateway,
                        batch_id=payload.batch_id,
                        pdf_path=source_path,
                        output_dir=default_import_batches_dir() / payload.batch_id / "vision_pages",
                    )
                    return self._task_repo.mark_completed(
                        task.task_id,
                        {
                            "document_type": "pdf",
                            "page_count": int(parsed.get("page_count") or 0),
                            "question_count": int(parsed.get("question_count") or 0),
                            "questions": parsed.get("questions") or [],
                            "media_assets": parsed.get("media_assets") or [],
                            "raw_text": parsed.get("raw_text") or "",
                            "page_results": parsed.get("page_results") or [],
                            "warnings": parsed.get("warnings") or [],
                            "parse_status": parsed.get("status") or "completed",
                        },
                    )

                parsed = await self._mcp_gateway.parse_document(mcp_input)
                questions = _normalize_ai_questions(
                    parsed.get("questions"),
                    batch_id=payload.batch_id,
                    source=payload.file_path,
                )
                return self._task_repo.mark_completed(
                    task.task_id,
                    {
                        "document_type": parsed.get("document_type") or payload.file_type,
                        "page_count": int(parsed.get("page_count") or len(parsed.get("pages", []) or []) or 1),
                        "question_count": len(questions),
                        "questions": questions,
                        "media_assets": parsed.get("media_assets") or [],
                        "raw_text": parsed.get("text") or parsed.get("raw_text") or "",
                    },
                )

            result = await self._document_parser.parse_document(mcp_input)

            questions = [
                normalize_import_question_metadata({
                    "question_id": q.question_id,
                    "question_type": q.question_type,
                    "title": q.title,
                    "options": [{"opt": o.opt, "content": o.content} for o in q.options],
                    "answer": q.answer,
                    "analysis": q.analysis,
                    "sub_questions": [],
                    "figures": [],
                    "difficulty": q.difficulty,
                    "knowledge_point": q.knowledge_point,
                    "tags": q.tags,
                    "source": payload.file_path,
                    "import_batch_id": payload.batch_id,
                    "confidence": q.confidence,
                    "source_page": q.source_page,
                    "source_region_id": q.source_region_id,
                    "raw_text": q.raw_text,
                })
                for q in result.questions
            ]

            return self._task_repo.mark_completed(
                task.task_id,
                {
                    "document_type": result.document_type,
                    "page_count": len(result.pages),
                    "question_count": len(questions),
                    "questions": questions,
                },
            )
        except AppError as exc:
            return self._task_repo.mark_failed(
                task.task_id,
                f"AI 文档解析失败 [{exc.code}]：{exc.message}",
            )
        except Exception as exc:  # noqa: BLE001
            return self._task_repo.mark_failed(
                task.task_id,
                f"AI 文档解析异常：{exc}",
            )

    # ── Shared ──

    def get_task(self, task_id: str) -> ImportTask:
        task = self._task_repo.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Import task not found: {task_id}")
        return task

    def list_review_tasks(self, limit: int = 80) -> list[ImportTask]:
        self._sync_review_workspace_context_tasks()
        task_types = [
            "ai_generated_review",
            "ai_generated_knowledge_review",
            "import_confirmed",
            "structure_questions",
            "ai_parse_document",
            "parse_structured_questions",
        ]
        if not hasattr(self._task_repo, "list"):
            return []
        tasks = self._task_repo.list(limit=limit, task_types=task_types)
        return [
            task
            for task in tasks
            if task.status in {"completed", "failed"}
            and (
                task.task_type in {"ai_generated_review", "ai_generated_knowledge_review", "import_confirmed"}
                or bool((task.result or {}).get("questions"))
                or bool((task.result or {}).get("knowledge_drafts"))
            )
        ]

    def delete_review_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task.status == "running":
            raise HTTPException(status_code=409, detail="Running review tasks cannot be deleted")
        sandbox_session_id = str((task.input_summary or {}).get("sandbox_session_id") or "").strip()
        if sandbox_session_id:
            self._mark_review_workspace_session_ignored(sandbox_session_id)
        delete = getattr(self._task_repo, "delete", None)
        if not callable(delete):
            raise HTTPException(status_code=503, detail="Review task deletion is not available")
        return bool(delete(task_id))

    def find_duplicate_review_tasks(
        self,
        *,
        task_type: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        tasks = self.list_review_tasks(limit=min(max(int(limit or 200), 1), 500))
        wanted_type = str(task_type or "").strip()
        wanted_source = " ".join(str(source or "").split()).casefold()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for task in tasks:
            if wanted_type and task.task_type != wanted_type:
                continue
            result = task.result or {}
            summary = task.input_summary or {}
            task_source = str(result.get("source") or summary.get("source") or "").strip()
            if wanted_source and wanted_source not in task_source.casefold():
                continue
            batch_id = str(result.get("batch_id") or summary.get("batch_id") or "").strip()
            source_sha256 = str(summary.get("input_sha256") or "").strip().lower()
            original_filename = ""
            if batch_id:
                try:
                    metadata = self._read_batch_metadata(batch_id)
                    source_sha256 = str(metadata.get("source_sha256") or source_sha256).strip().lower()
                    original_filename = str(metadata.get("original_filename") or "").strip()
                except HTTPException:
                    pass
            fallback = _duplicate_title(original_filename or task_source)
            key = f"sha256:{source_sha256}" if re.fullmatch(r"[0-9a-f]{64}", source_sha256) else f"source:{fallback}"
            if not fallback and not source_sha256:
                continue
            grouped.setdefault(key, []).append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "batch_id": batch_id,
                    "source": task_source,
                    "original_filename": original_filename,
                    "source_sha256": source_sha256 or None,
                    "question_count": int(result.get("question_count") or 0),
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                }
            )
        groups: list[dict[str, Any]] = []
        for key, items in grouped.items():
            if len(items) < 2:
                continue
            items.sort(key=lambda item: (item["updated_at"], item["task_id"]), reverse=True)
            groups.append(
                {
                    "duplicate_key": key,
                    "keep": items[0],
                    "delete_candidates": items[1:],
                    "count": len(items),
                }
            )
        groups.sort(key=lambda item: (-item["count"], item["duplicate_key"]))
        return {
            "ok": True,
            "groups": groups,
            "duplicate_group_count": len(groups),
            "delete_candidate_count": sum(len(item["delete_candidates"]) for item in groups),
        }

    def delete_review_tasks(self, task_ids: list[str]) -> dict[str, Any]:
        normalized = list(dict.fromkeys(str(item).strip() for item in task_ids if str(item).strip()))
        deleted: list[str] = []
        skipped: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []
        review_task_ids = {task.task_id for task in self.list_review_tasks(limit=500)}
        for task_id in normalized:
            try:
                if task_id not in review_task_ids:
                    failed.append({"task_id": task_id, "error": "该任务不是可删除的审核任务。"})
                    continue
                task = self.get_task(task_id)
                if task.status in {"pending", "running", "retrying", "cancel_requested"}:
                    skipped.append({"task_id": task_id, "reason": f"任务仍处于 {task.status} 状态。"})
                    continue
                if self.delete_review_task(task_id):
                    deleted.append(task_id)
                else:
                    failed.append({"task_id": task_id, "error": "任务未删除。"})
            except HTTPException as exc:
                failed.append({"task_id": task_id, "error": str(exc.detail)})
        return {
            "ok": not failed,
            "deleted": deleted,
            "skipped": skipped,
            "failed": failed,
            "summary": {
                "received": len(normalized),
                "deleted": len(deleted),
                "skipped": len(skipped),
                "failed": len(failed),
            },
        }

    def _sync_review_workspace_context_tasks(self) -> None:
        list_tasks = getattr(self._task_repo, "list", None)
        if not callable(list_tasks):
            return
        repo_db_path = getattr(self._task_repo, "_db_path", None)
        if repo_db_path:
            resolved_repo_path = Path(str(repo_db_path)).resolve()
            allowed_paths = {default_db_path().resolve(), default_review_db_path().resolve()}
            if resolved_repo_path not in allowed_paths:
                return
        workspace_path = default_review_db_path()
        if not workspace_path.exists():
            return
        try:
            existing = list_tasks(limit=200)
            existing_sessions = {
                str((task.input_summary or {}).get("sandbox_session_id") or "").strip()
                for task in existing
                if (task.input_summary or {}).get("sandbox_session_id")
            }
            ignored_sessions = self._ignored_review_workspace_sessions()
            grouped = self._load_review_workspace_knowledge_sessions(workspace_path)
            for session_id, drafts in grouped.items():
                if not session_id or session_id in existing_sessions or session_id in ignored_sessions or not drafts:
                    continue
                source = f"MCP 审核沙盒 · {session_id}"
                task = self._task_repo.create(
                    task_type="ai_generated_knowledge_review",
                    input_summary={
                        "source": source,
                        "sandbox_session_id": session_id,
                        "knowledge_count": len(drafts),
                    },
                )
                result = {
                    "batch_id": f"sandbox_{session_id}",
                    "source": source,
                    "title": f"审核沙盒知识点 · {session_id}",
                    "question_count": 0,
                    "knowledge_count": len(drafts),
                    "questions": [],
                    "knowledge_drafts": drafts,
                    "warnings": ["已从 MCP 审核沙盒同步到校对中心，请人工确认后再入库。"],
                    "page_results": [],
                    "media_assets": [],
                    "chat_context": f"review_workspace.sqlite3 session_id={session_id}",
                }
                self._task_repo.mark_completed(task.task_id, result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to sync review workspace context tasks: %s", exc)

    def _load_review_workspace_knowledge_sessions(self, workspace_path: Path) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        with sqlite3.connect(workspace_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, item_type, source_id, title, content, metadata_json, session_id, created_at
                FROM review_context_items
                WHERE item_type = 'knowledge'
                ORDER BY session_id, id
                """
            ).fetchall()
        for index, row in enumerate(rows, start=1):
            session_id = str(row["session_id"] or "review-workspace").strip()
            metadata = _safe_json_dict(row["metadata_json"])
            order = metadata.get("order") or index
            base_id = str(metadata.get("topic3_id") or row["source_id"] or f"sandbox_{session_id}").strip()
            draft_id = f"{base_id}-{int(order):02d}" if str(order).isdigit() else f"{base_id}-{row['id']}"
            keywords = metadata.get("keywords")
            grouped.setdefault(session_id, []).append(
                {
                    "draft_id": draft_id,
                    "topic3_id": draft_id,
                    "topic3_name": str(row["title"] or metadata.get("topic3_name") or draft_id).strip(),
                    "topic2_id": str(metadata.get("topic2_id") or "").strip(),
                    "topic2_name": str(metadata.get("topic2_name") or "").strip(),
                    "topic1_id": str(metadata.get("topic1_id") or "").strip(),
                    "topic1_name": str(metadata.get("topic1_name") or "").strip(),
                    "source_chapter": str(metadata.get("chapter") or metadata.get("source_chapter") or "").strip(),
                    "definition": str(row["content"] or "").strip(),
                    "formula": str(metadata.get("formula") or "").strip(),
                    "key_summary": str(row["content"] or "").strip(),
                    "error_prone": "",
                    "example_analysis": "",
                    "tags": [str(item) for item in keywords] if isinstance(keywords, list) else [],
                    "raw_text": str(row["content"] or ""),
                    "status": "pending",
                }
            )
        return grouped

    def _ignored_review_workspace_sessions(self) -> set[str]:
        ignored_db_path = default_review_db_path()
        ignored_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(ignored_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_workspace_ignored_sessions (
                    session_id TEXT PRIMARY KEY,
                    ignored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            rows = conn.execute("SELECT session_id FROM review_workspace_ignored_sessions").fetchall()
        return {str(row[0]) for row in rows}

    def _mark_review_workspace_session_ignored(self, session_id: str) -> None:
        ignored_db_path = default_review_db_path()
        ignored_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(ignored_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_workspace_ignored_sessions (
                    session_id TEXT PRIMARY KEY,
                    ignored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO review_workspace_ignored_sessions(session_id) VALUES (?)",
                (session_id,),
            )

def import_task_to_response(task: ImportTask) -> dict:
    return asdict(task)
