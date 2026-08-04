from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import shutil
import zipfile
from shutil import which
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)

IMPORT_PIPELINE_CONFIG_VERSION = os.getenv("PHYSICS_IMPORT_CONFIG_VERSION", "1").strip() or "1"
_BATCH_LOCKS: dict[str, _BatchProcessLock] = {}
_BATCH_LOCKS_GUARD = threading.Lock()


class StaleBatchVersionError(RuntimeError):
    """Raised when late worker output would overwrite newer user edits."""


class _BatchProcessLock:
    """Re-entrant process and filesystem lock for one batch metadata file."""

    def __init__(self, batch_id: str) -> None:
        self._batch_id = batch_id
        self._thread_lock = threading.RLock()
        self._local = threading.local()
        self._handle: Any | None = None

    def __enter__(self) -> _BatchProcessLock:
        self._thread_lock.acquire()
        depth = int(getattr(self._local, "depth", 0))
        try:
            if depth == 0:
                lock_path = default_import_batches_dir() / self._batch_id / ".pipeline.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = lock_path.open("a+b")
                self._acquire_file_lock(self._handle)
            self._local.depth = depth + 1
            return self
        except Exception:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        depth = int(getattr(self._local, "depth", 1)) - 1
        self._local.depth = depth
        try:
            if depth == 0 and self._handle is not None:
                self._release_file_lock(self._handle)
                self._handle.close()
                self._handle = None
        finally:
            self._thread_lock.release()

    @staticmethod
    def _acquire_file_lock(handle: Any) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            if handle.read(1) == b"":
                handle.write(b"0")
                handle.flush()
            deadline = time.monotonic() + 30
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for import batch lock")
                    time.sleep(0.05)
        else:  # pragma: no cover - exercised on non-Windows deployments
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _release_file_lock(handle: Any) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - exercised on non-Windows deployments
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

from ..paths import default_db_path, default_import_batches_dir, default_review_db_path, project_root
from ..repositories.import_tasks import ImportTask, InMemoryImportTaskRepository
from ..schemas.import_pipeline import (
    AiParseDocumentRequest,
    CleanDocumentRequest,
    ConvertDocumentRequest,
    ParseStructuredQuestionsRequest,
)
from .pdf_page_ocr import parse_pdf_by_page
from .question_splitter import ExamQuestionSplitter, is_clearly_experiment_question
from .math_text import normalize_question_math, normalize_short_inline_display_math

if TYPE_CHECKING:
    from mcp_contracts.src.contracts import DocumentParser  # type: ignore[import-not-found]
    from .mcp_gateway import McpGatewayService


class PandocAdapter:
    def __init__(self, executable: str = "pandoc") -> None:
        self._executable = executable

    def is_available(self) -> bool:
        return which(self._executable) is not None or self._markitdown_available()

    @staticmethod
    def _markitdown_available() -> bool:
        try:
            import markitdown  # noqa: F401
        except ImportError:
            return False
        return True

    def convert(self, source_path: str, target_format: str, output_path: str | None = None) -> dict[str, str]:
        if which(self._executable) is None:
            return self._markitdown_convert(source_path, target_format, output_path)

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
        if which(self._executable) is None:
            return self._markitdown_unpack_to_markdown(source_path, markdown_path, media_dir)

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

    def _markitdown_convert(self, source_path: str, target_format: str, output_path: str | None) -> dict[str, str]:
        if not self._markitdown_available():
            raise RuntimeError("Neither pandoc nor the MarkItDown fallback is available")
        if target_format not in {"markdown", "plain"}:
            raise RuntimeError("MarkItDown fallback supports Markdown or plain-text conversion only")
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        target = Path(output_path) if output_path else source.with_suffix(".md" if target_format == "markdown" else ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        from markitdown import MarkItDown

        converted = MarkItDown(enable_plugins=False).convert(str(source))
        text = str(getattr(converted, "text_content", ""))
        target.write_text(text, encoding="utf-8")
        return {"source_path": str(source), "output_path": str(target), "target_format": target_format, "text": text}

    def _markitdown_unpack_to_markdown(self, source_path: str, markdown_path: str, media_dir: str) -> dict:
        """Fallback for Word text when Pandoc is unavailable.

        This deliberately preserves the review boundary: converted content still enters
        an import batch and then the Review DB. Extracted Word media is retained for
        reviewers, but not artificially attached to a question when the fallback
        cannot determine a trustworthy anchor.
        """
        result = self._markitdown_convert(source_path, "markdown", markdown_path)
        source = Path(source_path)
        media = Path(media_dir)
        media.mkdir(parents=True, exist_ok=True)
        images: list[Path] = []
        if source.suffix.lower() == ".docx":
            with zipfile.ZipFile(source) as archive:
                for member in archive.namelist():
                    if not member.startswith("word/media/") or member.endswith("/"):
                        continue
                    target = media / Path(member).name
                    target.write_bytes(archive.read(member))
                    images.append(target)
            rewritten = self._rewrite_markitdown_docx_images(source, str(result.get("text") or ""))
            Path(markdown_path).write_text(rewritten, encoding="utf-8")
            result["text"] = rewritten
        return {
            **result,
            "media_dir": str(media),
            "image_count": len(images),
            "images": [str(path) for path in images],
            "conversion_engine": "markitdown_fallback",
            "warning": "Pandoc is unavailable. Images were preserved for review but require confirmation before question binding.",
        }

    @staticmethod
    def _rewrite_markitdown_docx_images(source: Path, markdown: str) -> str:
        """Replace MarkItDown data-URI placeholders with extracted DOCX media names."""
        try:
            with zipfile.ZipFile(source) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
                relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        except (KeyError, OSError, ET.ParseError, zipfile.BadZipFile):
            return markdown

        embed_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
        rid_to_filename = {
            str(node.attrib.get("Id") or ""): Path(str(node.attrib.get("Target") or "").replace("\\", "/")).name
            for node in relationships
            if str(node.attrib.get("Type") or "").endswith("/image")
        }

        drawing_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
        doc_pr_tag = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}docPr"
        blip_tag = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
        by_alt: dict[str, str] = {}
        ordered_filenames: list[str] = []
        for drawing in document.iter(drawing_tag):
            doc_pr = next(drawing.iter(doc_pr_tag), None)
            blip = next(drawing.iter(blip_tag), None)
            if blip is None:
                continue
            filename = rid_to_filename.get(str(blip.attrib.get(embed_key) or ""))
            if not filename:
                continue
            ordered_filenames.append(filename)
            if doc_pr is not None:
                for key in ("descr", "title", "name"):
                    alt = str(doc_pr.attrib.get(key) or "").strip()
                    if alt:
                        by_alt.setdefault(alt, filename)

        if not ordered_filenames:
            return markdown

        data_image = re.compile(r"!\[([^\]]*)\]\(data:image/[^)]*\)(?:\{[^}]*\})?", re.IGNORECASE)
        image_index = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal image_index
            alt = match.group(1).strip()
            filename = by_alt.get(alt)
            if filename is None and image_index < len(ordered_filenames):
                filename = ordered_filenames[image_index]
            image_index += 1
            if not filename:
                return match.group(0)
            return f"![{alt}]({filename})"

        return data_image.sub(replace, markdown)

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


def _document_title(filename: str) -> str:
    """Use the human document title as question provenance, never its suffix."""
    title = Path(str(filename or "")).stem.strip()
    return title or "未命名文档"


def _duplicate_title(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


_ANSWER_DIFFICULTY_RE = re.compile(r"【\s*难度\s*】\s*([01](?:\.\d+)?)", re.IGNORECASE)
_ANSWER_KNOWLEDGE_RE = re.compile(r"【\s*知识点\s*】\s*([^【\r\n]+)", re.IGNORECASE)
_MULTI_CHOICE_ANSWER_RE = re.compile(r"^[A-H]{2,}$")
_PROVINCES = (
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "全国",
)


def _normalize_source_name(value: Any) -> str:
    source = " ".join(str(value or "").split()).strip()
    if not source or "·" in source:
        return source
    year_match = re.search(r"(20\d{2})", source)
    province = next((item for item in _PROVINCES if item in source), "")
    if not year_match or not province or "高考" not in source:
        return source
    suffix = ""
    option_match = re.search(r"([（(]?\s*\d{1,2}\s*月选考\s*[)）]?)", source)
    if option_match:
        suffix = f"（{re.sub(r'[^0-9月选考]', '', option_match.group(1))}）"
    return f"{year_match.group(1)}年高考·{province}卷·物理{suffix}"


def _difficulty_level(score: float) -> int:
    if score >= 0.85:
        return 2
    if score >= 0.65:
        return 3
    if score >= 0.40:
        return 4
    return 5


def normalize_import_question_metadata(question: dict[str, Any]) -> dict[str, Any]:
    """Normalize metadata without changing the substantive question content."""
    normalized = dict(question)
    warnings = [str(item) for item in normalized.get("validation_warnings") or [] if str(item).strip()]
    answer = str(normalized.get("answer") or "").strip()
    difficulty_match = _ANSWER_DIFFICULTY_RE.search(answer)
    knowledge_match = _ANSWER_KNOWLEDGE_RE.search(answer)
    if difficulty_match:
        normalized["difficulty"] = _difficulty_level(float(difficulty_match.group(1)))
        answer = _ANSWER_DIFFICULTY_RE.sub("", answer)
        warnings.append("已从答案中提取难度元数据。")
    if knowledge_match:
        knowledge = knowledge_match.group(1).strip(" ，,;；。")
        if knowledge and not str(normalized.get("knowledge_point") or "").strip():
            normalized["knowledge_point"] = knowledge
        answer = _ANSWER_KNOWLEDGE_RE.sub("", answer)
        warnings.append("已从答案中提取知识点元数据。")
    answer = re.sub(r"\s{2,}", " ", answer).strip(" \t\r\n,，;；")
    normalized["answer"] = answer

    question_type = str(normalized.get("question_type") or "calculation").strip()
    compact_answer = re.sub(r"[^A-H]", "", answer.upper())
    experiment_text = "\n".join([
        str(normalized.get("title") or ""),
        *(str(option.get("content") or "") for option in normalized.get("options") or [] if isinstance(option, dict)),
    ])
    if question_type in {"single_choice", "multi_choice"} and is_clearly_experiment_question(experiment_text):
        normalized["question_type"] = "experiment"
        warnings.append("题干具有明确的多步骤实验结构，题型已修正为实验题。")
    elif question_type == "single_choice" and _MULTI_CHOICE_ANSWER_RE.fullmatch(compact_answer):
        normalized["question_type"] = "multi_choice"
        warnings.append("答案包含多个选项，题型已从单选修正为多选。")

    original_source = str(normalized.get("source_raw") or normalized.get("source") or "").strip()
    source = _normalize_source_name(normalized.get("source"))
    if original_source:
        normalized["source_raw"] = original_source
    if source:
        normalized["source"] = source
    if warnings:
        normalized["validation_warnings"] = list(dict.fromkeys(warnings))
    return normalized


def _source_extension(metadata: dict) -> str:
    return Path(str(metadata.get("stored_filename") or metadata.get("original_filename") or "")).suffix.lower().lstrip(".")


def _normalize_ai_questions(raw_questions: Any, batch_id: str, source: str) -> list[dict]:
    questions = raw_questions if isinstance(raw_questions, list) else []
    normalized: list[dict] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            normalize_import_question_metadata({
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
            })
        )
    return normalized


def _extract_json_payload(text: str) -> Any | None:
    candidates = [text.strip()]
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        candidates.append(match.group(1).strip())

    for candidate in candidates:
        if not candidate:
            continue
        start = min(
            [pos for pos in (candidate.find("{"), candidate.find("[")) if pos >= 0],
            default=-1,
        )
        if start < 0:
            continue
        snippet = candidate[start:]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue
    return None


def _safe_json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_generated_questions(source_text: str, batch_id: str, source: str) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    json_payload = _extract_json_payload(source_text)
    if isinstance(json_payload, dict):
        questions = _normalize_ai_questions(json_payload.get("questions") or [json_payload], batch_id, source)
        if questions:
            return questions, warnings
    if isinstance(json_payload, list):
        questions = _normalize_ai_questions(json_payload, batch_id, source)
        if questions:
            return questions, warnings

    block_questions = _parse_generated_question_blocks(source_text, batch_id, source)
    if block_questions:
        warnings.append("已按 AI 对话文本整理为待审核草稿，建议重点核对题干、答案和解析边界。")
        return block_questions, warnings

    splitter = ExamQuestionSplitter()
    split_result = splitter.split(source_text, batch_id=batch_id, source=source, media_assets=[])
    questions = split_result.get("questions") if isinstance(split_result, dict) else []
    if isinstance(questions, list) and questions:
        warnings.append("已按自然文本拆题，建议重点核对题干、答案和解析边界。")
        return questions, warnings

    fallback = _fallback_single_generated_question(source_text, batch_id, source, 1)
    if fallback:
        warnings.append("未识别到明确题号，已将当前 AI 回复整理为 1 条待审核草稿。")
        return [fallback], warnings
    return [], ["没有识别到可送审的试题，请让 AI 按“题干、选项、答案、解析”重新输出。"]


def _normalize_knowledge_draft(raw: Any, batch_id: str, index: int, source_text: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or raw.get("topic3_name") or raw.get("name") or "").strip()
    if not title:
        return None
    draft_id = str(raw.get("draft_id") or raw.get("topic3_id") or f"{batch_id}_k{index:04d}")
    tags = raw.get("tags")
    return {
        "draft_id": draft_id,
        "topic3_id": str(raw.get("topic3_id") or draft_id).strip(),
        "topic3_name": title,
        "topic2_id": str(raw.get("topic2_id") or raw.get("parent_id") or "").strip(),
        "topic2_name": str(raw.get("topic2_name") or raw.get("module") or "").strip(),
        "topic1_id": str(raw.get("topic1_id") or "").strip(),
        "topic1_name": str(raw.get("topic1_name") or "").strip(),
        "source_chapter": str(raw.get("source_chapter") or raw.get("chapter") or "").strip(),
        "definition": str(raw.get("definition") or raw.get("content") or "").strip(),
        "formula": str(raw.get("formula") or "").strip(),
        "key_summary": str(raw.get("key_summary") or raw.get("summary") or "").strip(),
        "error_prone": str(raw.get("error_prone") or raw.get("common_mistakes") or "").strip(),
        "example_analysis": str(raw.get("example_analysis") or raw.get("example") or "").strip(),
        "tags": [str(item) for item in tags] if isinstance(tags, list) else [],
        "raw_text": source_text,
        "status": "pending",
    }


def _extract_generated_knowledge_drafts(source_text: str, batch_id: str) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    json_payload = _extract_json_payload(source_text)
    candidates: list[Any] = []
    if isinstance(json_payload, dict):
        raw_items = json_payload.get("knowledge_drafts") or json_payload.get("knowledge_points")
        if isinstance(raw_items, list):
            candidates.extend(raw_items)
        else:
            candidates.append(json_payload)
    elif isinstance(json_payload, list):
        candidates.extend(json_payload)

    drafts: list[dict] = []
    for index, item in enumerate(candidates, start=1):
        draft = _normalize_knowledge_draft(item, batch_id, index, source_text)
        if draft:
            drafts.append(draft)
    if drafts:
        return drafts, warnings

    if re.search(r"(知识点|定义|公式|易错|核心|考点|key_summary|definition|formula|error_prone)", source_text):
        title_match = re.search(r"(?:知识点|标题|考点)\s*[：:]\s*([^\n]+)", source_text)
        title = title_match.group(1).strip() if title_match else source_text.strip().splitlines()[0][:60]
        drafts.append(
            {
                "draft_id": f"{batch_id}_k0001",
                "topic3_id": f"{batch_id}_k0001",
                "topic3_name": title,
                "topic2_id": "",
                "topic2_name": "",
                "topic1_id": "",
                "topic1_name": "",
                "source_chapter": "",
                "definition": source_text.strip(),
                "formula": "",
                "key_summary": "",
                "error_prone": "",
                "example_analysis": "",
                "tags": [],
                "raw_text": source_text,
                "status": "pending",
            }
        )
        warnings.append("已按知识点文本整理为待审核草稿，建议补全章节层级和标准知识点 ID。")
    return drafts, warnings


def _looks_like_knowledge_review(source_text: str) -> bool:
    payload = _extract_json_payload(source_text)
    if isinstance(payload, dict):
        if "knowledge_drafts" in payload or "knowledge_points" in payload:
            return True
        knowledge_keys = {"definition", "formula", "key_summary", "error_prone", "topic3_name"}
        question_keys = {"answer", "options", "question_body", "question_type"}
        if knowledge_keys.intersection(payload) and not question_keys.intersection(payload):
            return True
    return bool(
        re.search(r"(知识点|定义|核心公式|易错点|标准表述)", source_text)
        and not re.search(r"(答案|选项|A\.|B\.|题干|参考答案)", source_text)
    )


def _parse_generated_question_blocks(source_text: str, batch_id: str, source: str) -> list[dict]:
    text = source_text.strip()
    if not re.search(r"(答案|参考答案|解析|详解|分析|Answer|Ans\.?|Analysis|Solution|Explanation)\s*[：:]", text, flags=re.IGNORECASE):
        return []

    starts = list(re.finditer(r"(?m)^\s*(?:第\s*\d{1,3}\s*题\s*[：:]?|\d{1,3}\s*[\.、．]\s+)", text))
    if not starts:
        question = _fallback_single_generated_question(text, batch_id, source, 1)
        return [question] if question else []

    questions: list[dict] = []
    for index, match in enumerate(starts, start=1):
        end = starts[index].start() if index < len(starts) else len(text)
        block = text[match.start():end].strip()
        question = _fallback_single_generated_question(block, batch_id, source, index)
        if question:
            questions.append(question)
    return questions


def _fallback_single_generated_question(source_text: str, batch_id: str, source: str, index: int) -> dict | None:
    text = source_text.strip()
    if not text:
        return None
    if not re.search(r"(题干|答案|解析|选项|Answer|Analysis|Solution|A[\.、．)]|B[\.、．)]|第\s*\d+\s*题)", text, flags=re.IGNORECASE):
        return None

    answer_match = re.search(r"(?:参考答案|答案|答|Answer|Ans\.?)\s*[：:]\s*([\s\S]*?)(?=(?:解析|详解|分析|Analysis|Solution|Explanation)\s*[：:]|$)", text, flags=re.IGNORECASE)
    analysis_match = re.search(r"(?:解析|详解|分析|Analysis|Solution|Explanation)\s*[：:]\s*([\s\S]*)$", text, flags=re.IGNORECASE)
    stem_text = text[: answer_match.start()].strip() if answer_match else text
    stem_text = re.sub(r"^\s*(?:题干|试题|题目|Question|Stem)\s*[：:]\s*", "", stem_text, flags=re.IGNORECASE).strip()
    stem_text = re.sub(r"^\s*(?:第\s*\d{1,3}\s*题\s*[：:]?|\d{1,3}\s*[\.、．]\s*)", "", stem_text).strip()

    options: list[dict] = []
    stem_lines: list[str] = []
    for line in stem_text.splitlines():
        option_match = re.match(r"^\s*([A-H])\s*[\.、．)]\s*(.+)$", line)
        if option_match:
            options.append({"opt": option_match.group(1), "content": normalize_short_inline_display_math(option_match.group(2).strip())})
        else:
            stem_lines.append(line)

    stem = normalize_short_inline_display_math("\n".join(stem_lines).strip())
    if not stem:
        return None
    answer = normalize_short_inline_display_math(answer_match.group(1).strip()) if answer_match else ""
    analysis = normalize_short_inline_display_math(analysis_match.group(1).strip()) if analysis_match else ""
    return normalize_question_math(
        {
            "question_id": f"{batch_id}_q{index:04d}",
            "question_type": "single_choice" if options else "calculation",
            "title": stem,
            "options": options,
            "answer": answer,
            "analysis": analysis,
            "sub_questions": [],
            "figures": [],
            "difficulty": None,
            "knowledge_point": "",
            "tags": ["AI生成"],
            "source": source,
            "import_batch_id": batch_id,
            "raw_text": source_text,
            "confidence": 0.5,
        }
    )


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
        warnings: list[str] = []

        pandoc_task = self.run_batch_pandoc(
            batch_id, expected_input_version=expected_input_version
        )
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

        clean_task = self.run_batch_ai_clean(
            batch_id, use_ai=False, expected_input_version=expected_input_version
        )
        if clean_task.status == "failed":
            warnings.append(clean_task.error or "本地清洗失败，尝试继续结构化")

        structure_task = self.structure_batch_questions(
            batch_id, use_ai_refine=False, expected_input_version=expected_input_version
        )
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

    async def recognize_batch(
        self,
        batch_id: str,
        *,
        expected_input_version: int | None = None,
    ) -> dict:
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
            return await asyncio.to_thread(
                self._run_text_pipeline, batch_id, ext, expected_input_version
            )

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
                    "warnings": [task.error] if task.error else [],
                }
            result = task.result or {}
            result_warnings = [str(item) for item in result.get("warnings", []) if str(item).strip()]
            question_count = int(result.get("question_count") or 0)
            if question_count == 0 and result_warnings:
                return {
                    "task_id": task.task_id,
                    "batch_id": batch_id,
                    "status": "failed",
                    "pipeline": "vision_qwen_ocr",
                    "source_type": ext,
                    "question_count": 0,
                    "questions": [],
                    "media_assets": result.get("media_assets") or [],
                    "markdown_preview": str(result.get("raw_text") or ""),
                    "structured_by": "mcp_vl_qwen_ocr",
                    "ai_refined_count": 0,
                    "warnings": result_warnings,
                    "error": "OCR / 视觉识别未得到题目：" + "；".join(result_warnings[:3]),
                }
            return {
                "task_id": task.task_id,
                "batch_id": batch_id,
                "status": "completed",
                "pipeline": "vision_qwen_ocr",
                "source_type": ext,
                "question_count": question_count,
                "questions": result.get("questions") or [],
                "media_assets": result.get("media_assets") or [],
                "markdown_preview": str(result.get("raw_text") or ""),
                "structured_by": "mcp_vl_qwen_ocr",
                "ai_refined_count": 0,
                "warnings": result_warnings,
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

            with _batch_lock(batch_id):
                self._assert_input_version(batch_id, input_version)
                _atomic_write_text(cleaned_path, cleaned_text)
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
        return default_import_batches_dir() / batch_id / "status.json"

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
        metadata_path = self._batch_metadata_path(batch_id)
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail=f"Import batch not found: {batch_id}")
        with _batch_lock(batch_id):
            return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _write_batch_metadata(self, batch_id: str, metadata: dict) -> None:
        metadata_path = self._batch_metadata_path(batch_id)
        with _batch_lock(batch_id):
            _atomic_write_json(metadata_path, metadata)

    def _content_version(self, metadata: dict[str, Any]) -> int:
        return max(1, int(metadata.get("content_version") or 1))

    def _assert_input_version(self, batch_id: str, expected_version: int) -> dict[str, Any]:
        metadata = self._read_batch_metadata(batch_id)
        actual = self._content_version(metadata)
        if actual != expected_version:
            raise StaleBatchVersionError(
                f"Import batch {batch_id} changed from version {expected_version} to {actual}; late output was discarded"
            )
        return metadata

    def _idempotency_key(self, operation: str, batch_id: str, metadata: dict[str, Any]) -> str:
        source_hash = str(metadata.get("source_sha256") or "")
        if not source_hash:
            source_path = project_root() / str(metadata.get("source_path") or "")
            if source_path.exists():
                source_hash = _sha256_file(source_path)
        canonical = json.dumps(
            {
                "operation": operation,
                "batch_id": batch_id,
                "input_sha256": source_hash,
                "config_version": str(metadata.get("config_version") or IMPORT_PIPELINE_CONFIG_VERSION),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _result_is_valid(self, operation: str, task: ImportTask) -> bool:
        if task.status != "completed" or not isinstance(task.result, dict):
            return False
        result = task.result
        if task.result_file_path and not Path(task.result_file_path).exists():
            return False
        required_keys = {
            "pandoc": ("relative_markdown_path",),
            "ai_clean": ("relative_cleaned_markdown_path",),
            "ai_structure": ("raw_json_path", "normalized_json_path"),
        }.get(operation, ())
        for key in required_keys:
            raw = str(result.get(key) or "")
            if not raw:
                return False
            path = Path(raw)
            candidate = path if path.is_absolute() else project_root() / path
            if not candidate.exists():
                return False
        assets = result.get("media_assets") or result.get("images") or []
        if isinstance(assets, list):
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                raw_path = str(asset.get("relative_path") or asset.get("absolute_path") or "")
                if not raw_path:
                    continue
                asset_path = Path(raw_path)
                candidate = asset_path if asset_path.is_absolute() else project_root() / asset_path
                if not candidate.exists():
                    return False
        return True

    def _record_stage_checkpoint(
        self,
        batch_id: str,
        stage: str,
        task_id: str,
        input_version: int,
    ) -> None:
        with _batch_lock(batch_id):
            metadata = self._assert_input_version(batch_id, input_version)
            stages = dict(metadata.get("completed_stages") or {})
            stages[stage] = {
                "task_id": task_id,
                "input_version": input_version,
                "completed_at": _now_iso(),
            }
            metadata["completed_stages"] = stages
            metadata["updated_at"] = _now_iso()
            _atomic_write_json(self._batch_metadata_path(batch_id), metadata)

    def _cached_stage_task(self, batch_id: str, stage: str, input_version: int) -> ImportTask | None:
        metadata = self._read_batch_metadata(batch_id)
        checkpoint = (metadata.get("completed_stages") or {}).get(stage)
        if not isinstance(checkpoint, dict) or int(checkpoint.get("input_version") or 0) != input_version:
            return None
        task_id = str(checkpoint.get("task_id") or "")
        task = self._task_repo.get(task_id) if task_id else None
        return task if task and self._result_is_valid(stage, task) else None

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
        supported = {"pandoc", "ai_clean", "ai_structure", "recognize"}
        if operation not in supported:
            raise ValueError(f"Unsupported background import operation: {operation}")
        metadata = self._read_batch_metadata(batch_id)
        input_version = self._content_version(metadata)
        idempotency_key = self._idempotency_key(operation, batch_id, metadata)
        summary = {
            "batch_id": batch_id,
            "operation": operation,
            "input_version": input_version,
            "input_sha256": str(metadata.get("source_sha256") or ""),
            "config_version": str(metadata.get("config_version") or IMPORT_PIPELINE_CONFIG_VERSION),
        }
        if request_context:
            summary["request_context"] = {
                key: str(value)
                for key, value in request_context.items()
                if value is not None and key in {"source", "session_id", "operator"}
            }
        create_or_get = getattr(self._task_repo, "create_or_get", None)
        if callable(create_or_get):
            task, created = create_or_get(
                task_type=f"background_{operation}",
                input_summary=summary,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
            )
        else:
            task = self._task_repo.create(
                task_type=f"background_{operation}",
                input_summary=summary,
                max_attempts=max_attempts,
                idempotency_key=idempotency_key,
            )
            created = True
        should_dispatch = created
        if not created and (
            task.status in {"failed", "cancelled"}
            or (task.status == "completed" and not self._result_is_valid(operation, task))
        ):
            retry_key = f"{idempotency_key}:retry:{task.attempt + 1}"
            if callable(create_or_get):
                task, should_dispatch = create_or_get(
                    task_type=f"background_{operation}",
                    input_summary=summary,
                    max_attempts=max_attempts,
                    idempotency_key=retry_key,
                )
            else:
                task = self._task_repo.create(
                    task_type=f"background_{operation}",
                    input_summary=summary,
                    max_attempts=max_attempts,
                    idempotency_key=retry_key,
                )
                should_dispatch = True
        elif not created:
            should_dispatch = False
        metadata.update(
            {
                "status": "queued" if should_dispatch else task.status,
                "active_task_id": task.task_id,
                "active_operation": operation,
                "updated_at": _now_iso(),
            }
        )
        self._write_batch_metadata(batch_id, metadata)
        return task, should_dispatch

    def execute_background_batch_task(
        self,
        task_id: str,
        operation: str,
        batch_id: str,
    ) -> ImportTask:
        """Execute one persisted batch task. Exceptions are left for Dramatiq to retry."""
        import asyncio

        current = self.get_task(task_id)
        if current.status in {"completed", "failed", "cancel_requested", "cancelled"}:
            return current
        claim = getattr(self._task_repo, "claim", None)
        if callable(claim):
            running_task = claim(task_id, current_step=operation)
            if running_task is None:
                return self.get_task(task_id)
        else:
            running_task = self._task_repo.mark_running(
                task_id,
                current_step=operation,
                progress=max(1, current.progress),
            )
        expected_input_version = int(current.input_summary.get("input_version") or 1)
        with _batch_lock(batch_id):
            metadata = self._assert_input_version(batch_id, expected_input_version)
            metadata.update(
                {
                    "status": "running",
                    "active_task_id": task_id,
                    "active_operation": operation,
                    "updated_at": _now_iso(),
                }
            )
            _atomic_write_json(self._batch_metadata_path(batch_id), metadata)
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

        result["task_id"] = task_id
        with _batch_lock(batch_id):
            metadata = self._assert_input_version(batch_id, expected_input_version)
            metadata.update(
                {
                    "status": str(result.get("status") or "completed"),
                    "active_task_id": task_id,
                    "active_operation": operation,
                    "updated_at": _now_iso(),
                }
            )
            _atomic_write_json(self._batch_metadata_path(batch_id), metadata)
            completed = self._task_repo.mark_completed(task_id, result)
        return completed

    def mark_background_task_retrying(
        self,
        task_id: str,
        error: str,
        *,
        error_type: str = "TaskExecutionError",
        user_message: str | None = None,
        technical_details: str | None = None,
    ) -> ImportTask:
        task = self.get_task(task_id)
        batch_id = str(task.input_summary.get("batch_id") or "")
        if batch_id:
            metadata = self._read_batch_metadata(batch_id)
            expected = int(task.input_summary.get("input_version") or 1)
            if self._content_version(metadata) == expected:
                metadata.update(
                    {
                        "status": "retrying",
                        "active_task_id": task_id,
                        "error": error,
                        "updated_at": _now_iso(),
                    }
                )
                self._write_batch_metadata(batch_id, metadata)
        mark_retrying = getattr(self._task_repo, "mark_retrying", None)
        if callable(mark_retrying):
            return mark_retrying(
                task_id,
                error,
                error_type=error_type,
                user_message=user_message or "任务暂时失败，系统将自动重试",
                technical_details=technical_details or error,
            )
        return self._task_repo.mark_running(task_id)

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
        task = self.get_task(task_id)
        batch_id = str(task.input_summary.get("batch_id") or "")
        if batch_id:
            metadata = self._read_batch_metadata(batch_id)
            expected = int(task.input_summary.get("input_version") or 1)
            if self._content_version(metadata) == expected:
                metadata.update(
                    {
                        "status": "failed",
                        "active_task_id": task_id,
                        "error": error,
                        "updated_at": _now_iso(),
                    }
                )
                self._write_batch_metadata(batch_id, metadata)
        return self._task_repo.mark_failed(
            task_id,
            error,
            error_type=error_type,
            user_message=user_message or error,
            technical_details=technical_details or error,
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


def _batch_lock(batch_id: str) -> _BatchProcessLock:
    with _BATCH_LOCKS_GUARD:
        return _BATCH_LOCKS.setdefault(batch_id, _BatchProcessLock(batch_id))


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_task_to_response(task: ImportTask) -> dict:
    return asdict(task)
