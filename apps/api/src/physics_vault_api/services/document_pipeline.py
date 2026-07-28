from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import shutil
from shutil import which
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)

from ..paths import default_import_batches_dir, project_root
from ..repositories.import_tasks import ImportTask, InMemoryImportTaskRepository
from ..schemas.import_pipeline import (
    AiParseDocumentRequest,
    CleanDocumentRequest,
    ConvertDocumentRequest,
    ParseStructuredQuestionsRequest,
)
from .pdf_page_ocr import parse_pdf_by_page
from .question_splitter import ExamQuestionSplitter
from .math_text import normalize_question_math, normalize_short_inline_display_math

if TYPE_CHECKING:
    from mcp_contracts.src.contracts import DocumentParser  # type: ignore[import-not-found]
    from .mcp_gateway import McpGatewayService


class PandocAdapter:
    def __init__(self, executable: str = "pandoc") -> None:
        self._executable = executable

    def is_available(self) -> bool:
        return which(self._executable) is not None

    def convert(self, source_path: str, target_format: str, output_path: str | None = None) -> dict[str, str]:
        if not self.is_available():
            raise RuntimeError("pandoc is not installed or not available in PATH")

        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        if output_path:
            target = Path(output_path)
        else:
            suffix = {"markdown": ".md", "html": ".html", "plain": ".txt"}[target_format]
            target = source.with_suffix(suffix)

        command = [
            self._executable,
            str(source),
            "-o",
            str(target),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        # Read the converted text content for downstream clean/parse steps.
        text = self._read_output_text(target)

        return {
            "source_path": str(source),
            "output_path": str(target),
            "target_format": target_format,
            "text": text,
        }

    def unpack_to_markdown(self, source_path: str, markdown_path: str, media_dir: str) -> dict:
        if not self.is_available():
            raise RuntimeError("pandoc is not installed or not available in PATH")

        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        target = Path(markdown_path)
        media = Path(media_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        media.mkdir(parents=True, exist_ok=True)

        command = [
            self._executable,
            str(source),
            "-t",
            "markdown",
            "-o",
            str(target),
            f"--extract-media={media}",
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        text = self._read_output_text(target)
        images = [
            path
            for path in sorted(media.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
        ]
        return {
            "source_path": str(source),
            "output_path": str(target),
            "media_dir": str(media),
            "image_count": len(images),
            "images": [str(path) for path in images],
            "text": text,
        }

    @staticmethod
    def _read_output_text(target: Path) -> str:
        """Read output file content with encoding fallback."""
        if not target.exists():
            return ""
        # Try UTF-8 first, then GBK (common on Chinese Windows), then latin-1.
        for encoding in ("utf-8", "gbk", "latin-1"):
            try:
                return target.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        # Last resort: read as bytes and decode with error replacement.
        try:
            raw = target.read_bytes()
            return raw.decode("utf-8", errors="replace")
        except OSError:
            return ""


class DocumentCleaningService:
    HEADER_PATTERNS = [
        re.compile(r"^\s*第\s*\d+\s*页\s*$"),
        re.compile(r"^\s*共\s*\d+\s*页\s*$"),
    ]

    def clean(self, payload: CleanDocumentRequest) -> dict[str, str | int]:
        text = payload.source_text.replace("\r\n", "\n").replace("\r", "\n")

        if payload.normalize_math_delimiters:
            text = text.replace("\\(", "$").replace("\\)", "$")
            text = text.replace("\\[", "$$").replace("\\]", "$$")

        lines = text.split("\n")
        cleaned_lines: list[str] = []
        for line in lines:
            candidate = line
            if payload.normalize_whitespace:
                candidate = re.sub(r"[ \t]+", " ", candidate).strip()
            if payload.strip_headers_footers and any(p.match(candidate) for p in self.HEADER_PATTERNS):
                continue
            cleaned_lines.append(candidate)

        if payload.remove_blank_lines:
            compacted: list[str] = []
            last_blank = False
            for line in cleaned_lines:
                is_blank = line == ""
                if is_blank and last_blank:
                    continue
                compacted.append(line)
                last_blank = is_blank
            cleaned_lines = compacted

        cleaned_text = normalize_short_inline_display_math("\n".join(cleaned_lines).strip())
        return {
            "cleaned_text": cleaned_text,
            "original_length": len(payload.source_text),
            "cleaned_length": len(cleaned_text),
        }

    def clean_markdown_for_import(self, markdown: str, media_assets: list[dict]) -> dict:
        text = markdown.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\\(", "$").replace("\\)", "$")
        text = text.replace("\\[", "$$").replace("\\]", "$$")

        media_refs = {
            str(asset.get("filename", "")).lower()
            for asset in media_assets
            if asset.get("filename")
        }

        cleaned_lines: list[str] = []
        warnings: list[str] = []
        for raw_line in text.split("\n"):
            line = re.sub(r"[ \t]+", " ", raw_line).strip()
            if re.fullmatch(r"(第\s*)?\d+\s*(页|/|／)?\s*(共\s*\d+\s*页)?", line):
                continue
            if re.fullmatch(r"[-=_]{3,}", line):
                continue
            if line.lower().startswith("![](") and media_refs and not any(name in line.lower() for name in media_refs):
                warnings.append(f"Unmatched image reference kept: {line[:80]}")
            cleaned_lines.append(line)

        compacted: list[str] = []
        last_blank = False
        for line in cleaned_lines:
            is_blank = line == ""
            if is_blank and last_blank:
                continue
            compacted.append(line)
            last_blank = is_blank

        cleaned_text = normalize_short_inline_display_math("\n".join(compacted).strip())
        return {
            "cleaned_text": cleaned_text,
            "original_length": len(markdown),
            "cleaned_length": len(cleaned_text),
            "warnings": warnings,
        }


class StructuredQuestionParsingService:
    QUESTION_SPLIT = re.compile(r"\n(?=(?:\d+[\.\u3001]\s*))")

    def __init__(self) -> None:
        self._splitter = ExamQuestionSplitter()

    def parse(self, payload: ParseStructuredQuestionsRequest) -> dict:
        chunks = [chunk.strip() for chunk in self.QUESTION_SPLIT.split(payload.source_text) if chunk.strip()]
        questions = []
        for index, chunk in enumerate(chunks, start=1):
            questions.append(
                {
                    "question_id": f"{payload.import_batch_id}-q{index:04d}",
                    "question_type": "calculation",
                    "title": chunk,
                    "options": [],
                    "answer": "",
                    "analysis": "",
                    "sub_questions": [],
                    "figures": [],
                    "difficulty": None,
                    "knowledge_point": "",
                    "tags": [],
                    "source": payload.source_path or "",
                    "import_batch_id": payload.import_batch_id,
                }
            )
        return {
            "question_count": len(questions),
            "questions": questions,
        }

    def parse_markdown_with_images(self, markdown: str, batch_id: str, source: str, media_assets: list[dict]) -> dict:
        """Structural parse of exam Markdown via the enhanced splitter.

        Recognises question numbers / options / answers / analysis blocks and
        binds images to the batch media manifest via ![fig:uuid] placeholders.
        """
        return self._splitter.split(
            markdown=markdown,
            batch_id=batch_id,
            source=source,
            media_assets=media_assets,
        )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root().resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _safe_filename(filename: str) -> str:
    source = Path(filename).name
    stem = Path(source).stem.strip() or "document"
    suffix = Path(source).suffix.lower()
    stem = re.sub(r"[^\w\-.()\u4e00-\u9fff]+", "_", stem, flags=re.UNICODE).strip("._")
    return f"{stem[:80] or 'document'}{suffix}"


def _source_extension(metadata: dict) -> str:
    return Path(str(metadata.get("stored_filename") or metadata.get("original_filename") or "")).suffix.lower().lstrip(".")


def _normalize_ai_questions(raw_questions: Any, batch_id: str, source: str) -> list[dict]:
    questions = raw_questions if isinstance(raw_questions, list) else []
    normalized: list[dict] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "question_id": str(item.get("question_id") or f"{batch_id}-q{index:04d}"),
                "question_type": str(item.get("question_type") or "calculation"),
                "title": normalize_short_inline_display_math(str(item.get("title") or item.get("stem") or "")),
                "options": [
                    normalize_question_math({"options": [option]}).get("options", [option])[0]
                    for option in item.get("options")
                ] if isinstance(item.get("options"), list) else [],
                "answer": normalize_short_inline_display_math(str(item.get("answer") or "")),
                "analysis": normalize_short_inline_display_math(str(item.get("analysis") or "")),
                "sub_questions": item.get("sub_questions") if isinstance(item.get("sub_questions"), list) else [],
                "figures": item.get("figures") if isinstance(item.get("figures"), list) else [],
                "difficulty": item.get("difficulty"),
                "knowledge_point": str(item.get("knowledge_point") or ""),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "source": str(item.get("source") or source),
                "import_batch_id": str(item.get("import_batch_id") or batch_id),
                "confidence": item.get("confidence"),
                "source_page": item.get("source_page"),
                "source_region_id": item.get("source_region_id"),
                "raw_text": item.get("raw_text"),
            }
        )
    return normalized


def _metadata_question_payload(question: dict) -> dict:
    return {
        "question_id": question.get("question_id", ""),
        "question_type": question.get("question_type", ""),
        "title": question.get("title", ""),
        "options": question.get("options", []),
        "answer": question.get("answer", ""),
        "analysis": question.get("analysis", ""),
        "knowledge_point": question.get("knowledge_point", ""),
        "tags": question.get("tags", []),
        "source": question.get("source", ""),
    }


def _parse_draft_metadata_result(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items")
    if not isinstance(items, list):
        items = raw.get("questions") or raw.get("metadata")
    if not isinstance(items, list) or not items:
        raw_text = str(raw.get("text") or "").strip()
        if raw_text:
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, list):
                    items = parsed
                elif isinstance(parsed, dict):
                    items = parsed.get("items") or parsed.get("questions") or parsed.get("metadata") or []
            except json.JSONDecodeError:
                items = []
    if not isinstance(items, list):
        return {}

    parsed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("question_id") or item.get("id") or "").strip()
        if not qid:
            continue
        entry: dict[str, Any] = {}
        knowledge = item.get("knowledge_points", item.get("knowledgePoints", item.get("knowledge_point")))
        if isinstance(knowledge, list) and knowledge:
            entry["knowledge_points"] = str(knowledge[0]).strip()
        elif isinstance(knowledge, str) and knowledge.strip():
            entry["knowledge_points"] = knowledge.strip()
        tags = item.get("tags")
        if isinstance(tags, list):
            entry["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        source = item.get("source")
        if isinstance(source, str) and source.strip():
            entry["source"] = source.strip()
        parsed[qid] = entry
    return parsed


def _merge_draft_metadata(
    question: dict,
    patch: dict[str, Any],
    fields: list[str],
    force_overwrite: bool,
) -> tuple[dict, bool]:
    merged = dict(question)
    changed = False

    if "knowledge_points" in fields:
        value = str(patch.get("knowledge_points") or "").strip()
        if value and (force_overwrite or not str(merged.get("knowledge_point") or "").strip()):
            merged["knowledge_point"] = value
            changed = True

    if "tags" in fields:
        tags = patch.get("tags") if isinstance(patch.get("tags"), list) else []
        tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        existing = merged.get("tags") if isinstance(merged.get("tags"), list) else []
        if tags and (force_overwrite or not existing):
            merged["tags"] = tags if force_overwrite else list(dict.fromkeys([*existing, *tags]))
            changed = True

    if "source" in fields:
        value = str(patch.get("source") or "").strip()
        if value and (force_overwrite or not str(merged.get("source") or "").strip()):
            merged["source"] = value
            changed = True

    return merged, changed


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

    # Batch-based import pipeline

    def create_batch_from_upload(self, filename: str, content: bytes) -> dict:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        batch_dir = default_import_batches_dir() / batch_id
        source_dir = batch_dir / "source"
        for directory in (source_dir, batch_dir / "pandoc", batch_dir / "ai", batch_dir / "logs"):
            directory.mkdir(parents=True, exist_ok=True)

        stored_filename = _safe_filename(filename)
        source_path = source_dir / stored_filename
        source_path.write_bytes(content)

        created_at = _now_iso()
        metadata = {
            "batch_id": batch_id,
            "status": "uploaded",
            "original_filename": filename,
            "stored_filename": stored_filename,
            "source_path": _relative_to_project(source_path),
            "created_at": created_at,
            "updated_at": created_at,
            "image_count": 0,
            "question_count": 0,
        }
        self._write_batch_metadata(batch_id, metadata)
        return {
            "batch_id": batch_id,
            "original_filename": filename,
            "stored_filename": stored_filename,
            "source_path": str(source_path),
            "relative_source_path": _relative_to_project(source_path),
            "status": "uploaded",
            "created_at": datetime.fromisoformat(created_at),
        }

    def run_batch_pandoc(self, batch_id: str) -> ImportTask:
        metadata = self._read_batch_metadata(batch_id)
        source_path = project_root() / metadata["source_path"]
        batch_dir = default_import_batches_dir() / batch_id
        markdown_path = batch_dir / "pandoc" / "document.md"
        media_dir = batch_dir / "pandoc" / "media"

        task = self._task_repo.create(
            task_type="pandoc_unpack",
            input_summary={"batch_id": batch_id, "source_path": metadata["source_path"]},
        )
        self._task_repo.mark_running(task.task_id)
        try:
            result = self._pandoc.unpack_to_markdown(
                source_path=str(source_path),
                markdown_path=str(markdown_path),
                media_dir=str(media_dir),
            )
            images = self._collect_media_assets(result["images"])
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
            (batch_dir / "pandoc" / "media_manifest.json").write_text(
                json.dumps(images, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            metadata.update(
                {
                    "status": "pandoc_completed",
                    "markdown_path": response["relative_markdown_path"],
                    "media_dir": response["relative_media_dir"],
                    "image_count": len(images),
                    "updated_at": _now_iso(),
                }
            )
            self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_completed(task.task_id, response)
        except Exception as exc:  # noqa: BLE001
            metadata.update({"status": "failed", "updated_at": _now_iso(), "error": str(exc)})
            self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_failed(task.task_id, str(exc))

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
            manifest_path.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
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

    def _run_text_pipeline(self, batch_id: str, ext: str) -> dict:
        """Synchronous text-document pipeline (run in a thread by recognize_batch)."""
        warnings: list[str] = []

        pandoc_task = self.run_batch_pandoc(batch_id)
        if pandoc_task.status == "failed":
            return {
                "batch_id": batch_id,
                "status": "failed",
                "pipeline": "word_pandoc_local",
                "source_type": ext,
                "question_count": 0,
                "questions": [],
                "error": pandoc_task.error,
            }

        clean_task = self.run_batch_ai_clean(batch_id, use_ai=False)
        if clean_task.status == "failed":
            warnings.append(clean_task.error or "本地清洗失败，尝试继续结构化")

        structure_task = self.structure_batch_questions(batch_id, use_ai_refine=False)
        if structure_task.status == "failed":
            return {
                "batch_id": batch_id,
                "status": "failed",
                "pipeline": "word_pandoc_local",
                "source_type": ext,
                "question_count": 0,
                "questions": [],
                "error": structure_task.error,
            }

        result = structure_task.result or {}
        pandoc_result = pandoc_task.result or {}
        clean_result = clean_task.result or {}
        warnings.extend(str(item) for item in clean_result.get("warnings", []) if str(item).strip())
        return {
            "task_id": structure_task.task_id,
            "batch_id": batch_id,
            "status": "completed",
            "pipeline": "word_pandoc_local",
            "source_type": ext,
            "question_count": int(result.get("question_count") or 0),
            "questions": result.get("questions") or [],
            "media_assets": result.get("media_assets") or pandoc_result.get("images") or [],
            "markdown_preview": str(clean_result.get("cleaned_preview") or pandoc_result.get("markdown_preview") or ""),
            "structured_by": str(result.get("structured_by") or ""),
            "ai_refined_count": int(result.get("ai_refined_count") or 0),
            "warnings": warnings,
        }

    async def recognize_batch(self, batch_id: str) -> dict:
        """Unified import router used by the smart recognition page.

        - Word/text documents: Pandoc unpack -> local clean -> local splitter.
          DeepSeek cleanup is intentionally left as a manual second pass.
        - PDF/images: MCP-VL/OCR, intended for Qwen-VL compatible models.
        """
        import asyncio
        metadata = self._read_batch_metadata(batch_id)
        ext = _source_extension(metadata)

        if ext in {"doc", "docx", "md", "markdown", "txt", "html"}:
            # Run the text pipeline in a thread to avoid blocking the event loop
            # (Pandoc, AI clean, and AI structure all do blocking I/O).
            return await asyncio.to_thread(self._run_text_pipeline, batch_id, ext)

        if ext in {"pdf", "jpg", "jpeg", "png", "webp"}:
            metadata = self._read_batch_metadata(batch_id)
            source_path = project_root() / metadata["source_path"]
            task = await self.ai_parse_document(
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
            if task.status == "failed":
                return {
                    "task_id": task.task_id,
                    "batch_id": batch_id,
                    "status": "failed",
                    "pipeline": "vision_qwen_ocr",
                    "source_type": ext,
                    "question_count": 0,
                    "questions": [],
                    "error": task.error,
                }
            result = task.result or {}
            return {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "completed",
                "pipeline": "vision_qwen_ocr",
                "source_type": ext,
                "question_count": int(result.get("question_count") or 0),
                "questions": result.get("questions") or [],
                "media_assets": result.get("media_assets") or [],
                "markdown_preview": str(result.get("raw_text") or ""),
                "structured_by": "mcp_vl_qwen_ocr",
                "ai_refined_count": 0,
                "warnings": warnings,
            }

        return {
            "batch_id": batch_id,
            "status": "failed",
            "pipeline": "word_pandoc_deepseek",
            "source_type": ext or "unknown",
            "question_count": 0,
            "questions": [],
            "error": f"不支持的文件类型：{ext or 'unknown'}",
        }

    def run_batch_ai_clean(self, batch_id: str, use_ai: bool = True) -> ImportTask:
        metadata = self._read_batch_metadata(batch_id)
        batch_dir = default_import_batches_dir() / batch_id
        markdown_path = project_root() / metadata["markdown_path"]
        manifest_path = batch_dir / "pandoc" / "media_manifest.json"
        cleaned_path = batch_dir / "ai" / "cleaned.md"

        task = self._task_repo.create(
            task_type="ai_clean_markdown",
            input_summary={"batch_id": batch_id, "markdown_path": metadata.get("markdown_path")},
        )
        self._task_repo.mark_running(task.task_id)
        try:
            markdown = PandocAdapter._read_output_text(markdown_path)
            media_assets = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
            fallback_result = self._cleaner.clean_markdown_for_import(markdown, media_assets)
            cleaned_text = str(fallback_result["cleaned_text"])
            warnings = list(fallback_result.get("warnings", []))
            cleaned_by = "local_cleaner"

            if use_ai and self._mcp_gateway is not None:
                try:
                    ai_result: dict[str, Any] = self._mcp_gateway.clean_import_markdown(markdown, media_assets)
                    ai_text = str(ai_result.get("cleaned_markdown") or ai_result.get("text") or "").strip()
                    # Guard: never accept a JSON wrapper as cleaned markdown
                    if ai_text.startswith("{") and "cleaned_markdown" in ai_text:
                        try:
                            nested = json.loads(ai_text)
                            if isinstance(nested, dict):
                                ai_text = str(nested.get("cleaned_markdown") or "").strip()
                            else:
                                ai_text = ""
                        except json.JSONDecodeError:
                            ai_text = ""
                    if ai_text and not ai_text.lstrip().startswith("{"):
                        cleaned_text = ai_text
                        cleaned_by = "mcp_llm"
                        ai_warnings = ai_result.get("warnings", [])
                        if isinstance(ai_warnings, list):
                            warnings.extend(str(item) for item in ai_warnings if str(item).strip())
                    else:
                        warnings.append("AI 清洗未返回 cleaned_markdown，已使用本地清洗结果。")
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"AI 清洗不可用，已使用本地清洗结果：{exc}")

            cleaned_path.write_text(cleaned_text, encoding="utf-8")
            response = {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "ai_clean_completed",
                "cleaned_markdown_path": str(cleaned_path),
                "relative_cleaned_markdown_path": _relative_to_project(cleaned_path),
                "cleaned_preview": cleaned_text[:2000],
                "text": cleaned_text,
                "cleaned_by": cleaned_by,
                "warnings": warnings,
            }
            metadata.update(
                {
                    "status": "ai_clean_completed",
                    "cleaned_markdown_path": response["relative_cleaned_markdown_path"],
                    "updated_at": _now_iso(),
                }
            )
            self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_completed(task.task_id, response)
        except Exception as exc:  # noqa: BLE001
            metadata.update({"status": "failed", "updated_at": _now_iso(), "error": str(exc)})
            self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_failed(task.task_id, str(exc))

    def structure_batch_questions(self, batch_id: str, use_ai_refine: bool = True) -> ImportTask:
        metadata = self._read_batch_metadata(batch_id)
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
        self._task_repo.mark_running(task.task_id)
        try:
            markdown = PandocAdapter._read_output_text(markdown_path)
            media_assets = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
            result = self._parser.parse_markdown_with_images(
                markdown=markdown,
                batch_id=batch_id,
                source=metadata.get("original_filename") or metadata.get("source_path") or "",
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

            response = {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "ai_completed",
                "question_count": len(questions),
                "questions": questions,
                "raw_json_path": str(raw_json_path),
                "normalized_json_path": str(normalized_json_path),
                "structured_by": structured_by,
                "ai_refined_count": ai_refined_count,
                "media_assets": media_assets,
            }
            raw_json_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
            normalized_json_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata.update(
                {
                    "status": "ai_completed",
                    "question_count": len(questions),
                    "raw_json_path": _relative_to_project(raw_json_path),
                    "normalized_json_path": _relative_to_project(normalized_json_path),
                    "updated_at": _now_iso(),
                }
            )
            self._write_batch_metadata(batch_id, metadata)
            return self._task_repo.mark_completed(task.task_id, response)
        except Exception as exc:  # noqa: BLE001
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

    def confirm_batch_questions(self, batch_id: str, questions: list[dict]) -> ImportTask:
        """Persist user-edited questions and expose them as a completed task.

        The review workbench loads import tasks by id, so wrapping the edited
        list in a completed task lets the existing /review/{taskId} flow pick
        it up without any changes.
        """
        metadata = self._read_batch_metadata(batch_id)
        batch_dir = default_import_batches_dir() / batch_id
        edited_path = batch_dir / "ai" / "questions.edited.json"
        edited_path.parent.mkdir(parents=True, exist_ok=True)
        edited_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

        # Regenerate stable question ids in order (user may have deleted/merged)
        for index, q in enumerate(questions, start=1):
            q["question_id"] = f"{batch_id}_q{index:04d}"
            q["import_batch_id"] = batch_id

        edited_path.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

        task = self._task_repo.create(
            task_type="import_confirmed",
            input_summary={"batch_id": batch_id, "question_count": len(questions)},
        )
        self._task_repo.mark_running(task.task_id)
        result = {
            "task_id": task.task_id,
            "batch_id": batch_id,
            "status": "confirmed",
            "question_count": len(questions),
            "questions": questions,
            "edited_json_path": str(edited_path),
        }
        metadata.update(
            {
                "status": "confirmed",
                "question_count": len(questions),
                "edited_json_path": _relative_to_project(edited_path),
                "updated_at": _now_iso(),
            }
        )
        self._write_batch_metadata(batch_id, metadata)
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
        target.write_bytes(content)

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
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return asset

    def _batch_metadata_path(self, batch_id: str) -> Path:
        return default_import_batches_dir() / batch_id / "status.json"

    def _read_batch_metadata(self, batch_id: str) -> dict:
        metadata_path = self._batch_metadata_path(batch_id)
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail=f"Import batch not found: {batch_id}")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _write_batch_metadata(self, batch_id: str, metadata: dict) -> None:
        metadata_path = self._batch_metadata_path(batch_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

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

    def convert_document(self, payload: ConvertDocumentRequest) -> ImportTask:
        task = self._task_repo.create(
            task_type="convert_document",
            input_summary={
                "source_path": payload.source_path,
                "source_type": payload.source_type,
                "target_format": payload.target_format,
            },
        )
        self._task_repo.mark_running(task.task_id)
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
        self._task_repo.mark_running(task.task_id)
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
        self._task_repo.mark_running(task.task_id)
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
        self._task_repo.mark_running(task.task_id)

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
                {
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
                }
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


def import_task_to_response(task: ImportTask) -> dict:
    return asdict(task)
