"""PDF page rendering and page-level OCR orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..paths import project_root
from .workflow_concurrency import gather_limited
from .math_text import normalize_question_math

logger = logging.getLogger(__name__)

DEFAULT_PDF_PAGE_CONCURRENCY = 2
DEFAULT_MAX_PDF_PAGES = 30


async def parse_pdf_by_page(
    *,
    gateway: Any,
    batch_id: str,
    pdf_path: Path,
    output_dir: Path,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
    concurrency: int = DEFAULT_PDF_PAGE_CONCURRENCY,
) -> dict[str, Any]:
    """Render a PDF to page images and OCR each page independently."""

    page_images = render_pdf_pages(pdf_path=pdf_path, output_dir=output_dir, max_pages=max_pages)
    if not page_images:
        return {
            "document_type": "pdf",
            "page_count": 0,
            "question_count": 0,
            "questions": [],
            "media_assets": [],
            "raw_text": "",
            "page_results": [],
            "warnings": ["PDF 未渲染出可识别页面"],
        }

    async def parse_page(page: tuple[int, Path]) -> dict[str, Any]:
        page_no, image_path = page
        try:
            parsed = await gateway.parse_document(
                {
                    "batch_id": f"{batch_id}_p{page_no:04d}",
                    "file_path": str(image_path),
                    "file_type": "png",
                    "mode": "image_document",
                    "enable_preprocess": True,
                    "enable_region_detection": True,
                    "enable_figure_extraction": True,
                    "enable_table_extraction": True,
                    "formula_format": "latex",
                    "ignore_headers_footers": True,
                }
            )
            questions = _normalize_page_questions(
                parsed.get("questions"),
                batch_id=batch_id,
                source=str(pdf_path),
                page_no=page_no,
            )
            regions = [
                {
                    "region_id": question.get("source_region_id"),
                    "question_id": question.get("question_id"),
                    "bbox": question.get("source_bbox"),
                }
                for question in questions
                if question.get("source_bbox")
            ]
            image_width, image_height = _image_size(image_path)
            return {
                "page_no": page_no,
                "status": "completed",
                "page_image_path": _relative_to_project(image_path),
                "question_count": len(questions),
                "questions": questions,
                "media_assets": parsed.get("media_assets") or [],
                "raw_text": str(parsed.get("text") or parsed.get("raw_text") or ""),
                "image_width": image_width,
                "image_height": image_height,
                "regions": regions,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("PDF page OCR failed for %s page %d: %s", pdf_path, page_no, exc)
            return {
                "page_no": page_no,
                "status": "failed",
                "page_image_path": _relative_to_project(image_path),
                "question_count": 0,
                "questions": [],
                "media_assets": [],
                "raw_text": "",
                "error": str(exc),
            }

    page_results = await gather_limited(page_images, concurrency, parse_page)
    page_results = sorted(page_results, key=lambda item: int(item.get("page_no") or 0))

    questions: list[dict[str, Any]] = []
    media_assets: list[dict[str, Any]] = []
    raw_text_parts: list[str] = []
    warnings: list[str] = []

    for result in page_results:
        questions.extend(result.get("questions") or [])
        media_assets.extend(result.get("media_assets") or [])
        raw_text = str(result.get("raw_text") or "").strip()
        if raw_text:
            raw_text_parts.append(raw_text)
        if result.get("status") == "failed":
            warnings.append(f"第 {result.get('page_no')} 页识别失败：{result.get('error')}")

    return {
        "document_type": "pdf",
        "page_count": len(page_images),
        "question_count": len(questions),
        "questions": questions,
        "media_assets": media_assets,
        "raw_text": "\n\n".join(raw_text_parts),
        "page_results": page_results,
        "warnings": warnings,
        "status": "partial_failed" if warnings else "completed",
    }


def render_pdf_pages(
    *,
    pdf_path: Path,
    output_dir: Path,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> list[tuple[int, Path]]:
    """Render PDF pages as PNG files for page-level OCR."""

    try:
        import pypdfium2 as pdfium
    except ModuleNotFoundError as exc:
        raise RuntimeError("PDF 按页识别需要安装 pypdfium2") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(pdf_path))
    page_count = min(len(pdf), max_pages)
    page_images: list[tuple[int, Path]] = []

    for page_index in range(page_count):
        page_no = page_index + 1
        target = output_dir / f"page_{page_no:04d}.png"
        if not target.exists():
            page = pdf[page_index]
            bitmap = page.render(scale=2.0)
            bitmap.to_pil().save(target)
        page_images.append((page_no, target))

    return page_images


def _normalize_page_questions(
    raw_questions: Any,
    *,
    batch_id: str,
    source: str,
    page_no: int,
) -> list[dict[str, Any]]:
    questions = raw_questions if isinstance(raw_questions, list) else []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            normalize_question_math({
                "question_id": str(item.get("question_id") or f"{batch_id}_p{page_no:04d}_q{index:04d}"),
                "question_type": _normalize_question_type(item.get("question_type")),
                "title": str(item.get("title") or item.get("stem") or ""),
                "options": _normalize_options(item.get("options")),
                "answer": str(item.get("answer") or ""),
                "analysis": str(item.get("analysis") or ""),
                "sub_questions": item.get("sub_questions") if isinstance(item.get("sub_questions"), list) else [],
                "figures": item.get("figures") if isinstance(item.get("figures"), list) else [],
                "difficulty": item.get("difficulty"),
                "knowledge_point": str(item.get("knowledge_point") or ""),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "source": str(item.get("source") or source),
                "import_batch_id": str(item.get("import_batch_id") or batch_id),
                "confidence": item.get("confidence"),
                "source_page": _safe_page_no(item.get("source_page"), page_no),
                "source_region_id": item.get("source_region_id"),
                "source_bbox": _normalize_source_bbox(
                    item.get("source_bbox") or item.get("region_bbox") or item.get("bbox")
                ),
                "raw_text": item.get("raw_text"),
            })
        )
    return normalized


def _image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:  # pragma: no cover - metadata enhancement only
        return None, None


def _normalize_source_bbox(value: Any) -> list[float] | None:
    """Return a canonical [x, y, width, height] region box."""

    if isinstance(value, dict):
        try:
            x = float(value.get("x", value.get("left", value.get("x1"))))
            y = float(value.get("y", value.get("top", value.get("y1"))))
            if value.get("width") is not None and value.get("height") is not None:
                width = float(value["width"])
                height = float(value["height"])
            else:
                width = float(value.get("right", value.get("x2"))) - x
                height = float(value.get("bottom", value.get("y2"))) - y
            return [x, y, max(0.0, width), max(0.0, height)]
        except (TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            x1, y1, third, fourth = [float(item) for item in value]
        except (TypeError, ValueError):
            return None
        # Vision providers commonly return [x1, y1, x2, y2]. Normalized
        # [x, y, width, height] values are preserved when the last pair does
        # not look like bottom-right coordinates.
        if third > x1 and fourth > y1:
            return [x1, y1, third - x1, fourth - y1]
        return [x1, y1, max(0.0, third), max(0.0, fourth)]
    return None


def _safe_page_no(value: Any, fallback: int) -> int:
    try:
        return int(value or fallback)
    except (TypeError, ValueError):
        return fallback


def _normalize_question_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    labels = {
        "单选": "single_choice",
        "单选题": "single_choice",
        "single": "single_choice",
        "single_choice": "single_choice",
        "多选": "multi_choice",
        "多选题": "multi_choice",
        "multi": "multi_choice",
        "multi_choice": "multi_choice",
        "填空": "fill",
        "填空题": "fill",
        "fill": "fill",
        "实验": "experiment",
        "实验题": "experiment",
        "experiment": "experiment",
        "计算": "calculation",
        "计算题": "calculation",
        "calculation": "calculation",
    }
    return labels.get(raw, "calculation")


def _normalize_options(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        default_opt = chr(ord("A") + index)
        if isinstance(item, dict):
            opt = str(item.get("opt") or default_opt).strip().rstrip(".")
            content = str(item.get("content") or item.get("text") or "").strip()
        else:
            text = str(item).strip()
            if len(text) >= 2 and text[0].upper() in "ABCDEFG" and text[1] in {".", "、", "．"}:
                opt = text[0].upper()
                content = text[2:].strip()
            else:
                opt = default_opt
                content = text
        if opt and content:
            normalized.append({"opt": opt.upper(), "content": content})
    return normalized


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root().resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
