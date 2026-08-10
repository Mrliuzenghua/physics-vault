"""Prepare an Obsidian-standardized question bank for review-center import.

This tool deliberately does not access either SQLite database.  It validates
the Markdown/image pair, copies assets into the application's question-assets
directory, and produces small JSON payloads for the controlled MCP review
import route.  Keeping the database write in MCP preserves the project's
canonical/review boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ANSWER_MARKERS = ("答案", "知识点", "详解", "解析")


@dataclass(frozen=True)
class PreparedQuestion:
    question_id: str
    payload: dict[str, Any]
    images: tuple[str, ...]


def _read_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing YAML front matter")
    match = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n?", text)
    if match is None:
        raise ValueError(f"{path.name}: malformed YAML front matter")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{path.name}: front matter must be a mapping")
    return metadata, text[match.end() :]


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _section_value(body: str, name: str) -> str:
    marker = re.escape(f"【{name}】")
    stops = "|".join(re.escape(f"【{item}】") for item in ANSWER_MARKERS if item != name)
    found = re.search(rf"{marker}\s*([\s\S]*?)(?=\n(?:{stops})|\Z)", body)
    return found.group(1).strip() if found else ""


def _remove_heading_noise(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        compact = line.strip()
        if compact.startswith("# 第") and compact.endswith("题"):
            continue
        if compact in {"## 原始切片", "## 标准化图片"}:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_options(stem: str) -> tuple[str, list[dict[str, str]]]:
    options: list[dict[str, str]] = []
    retained: list[str] = []
    for line in stem.splitlines():
        plain = re.sub(r"^\s*>\s?", "", line).strip()
        option = re.match(r"^([A-H])\s*[\.．、\)]\s*(.+)$", plain)
        if option:
            options.append({"opt": option.group(1), "content": option.group(2).strip()})
        else:
            retained.append(line)
    return "\n".join(retained).strip(), options


def _images_from_metadata(metadata: dict[str, Any], question_id: str) -> list[dict[str, str]]:
    declared = metadata.get("standardized_assets")
    rows = declared if isinstance(declared, list) else []
    figures: list[dict[str, str]] = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if not filename:
            continue
        figures.append(
            {
                "fig_uuid": str(item.get("asset_id") or f"{question_id}-img{index:02d}"),
                "local_path": f"data/assets/questions/obsidian-vault2/{filename}",
                "role": str(item.get("role") or "stem"),
                "display_scale": 60,
            }
        )
    if figures:
        return figures

    raw_images = metadata.get("images") if isinstance(metadata.get("images"), list) else []
    raw_ids = metadata.get("image_ids") if isinstance(metadata.get("image_ids"), list) else []
    for index, raw_filename in enumerate(raw_images, start=1):
        filename = str(raw_filename).strip()
        if not filename:
            continue
        figures.append(
            {
                "fig_uuid": str(raw_ids[index - 1] if index <= len(raw_ids) else f"{question_id}-img{index:02d}"),
                "local_path": f"data/assets/questions/obsidian-vault2/{filename}",
                "role": "stem",
                "display_scale": 60,
            }
        )
    return figures


def _prepare_question(path: Path) -> PreparedQuestion:
    metadata, body = _read_front_matter(path.read_text(encoding="utf-8"), path)
    question_id = str(metadata.get("question_id") or metadata.get("id") or "").strip()
    if not re.fullmatch(r"Q\d{8}", question_id):
        raise ValueError(f"{path.name}: invalid question id {question_id!r}")

    # The final standardized-image appendix duplicates the image list and is
    # not part of the question stem.
    question_body = body.split("\n## 标准化图片", maxsplit=1)[0]
    question_body = _remove_heading_noise(question_body)
    figures = _images_from_metadata(metadata, question_id)
    for figure in figures:
        filename = Path(figure["local_path"]).name
        question_body = re.sub(
            rf"!\[\[[^\]]*{re.escape(filename)}\]\]",
            f"![fig:{figure['fig_uuid']}]",
            question_body,
        )

    answer = _section_value(question_body, "答案")
    knowledge = _section_value(question_body, "知识点")
    analysis = _section_value(question_body, "详解") or _section_value(question_body, "解析")
    stem = re.split(r"\n【(?:答案|知识点|详解|解析)】", question_body, maxsplit=1)[0].strip()
    stem, options = _extract_options(stem)
    stem = "\n".join(re.sub(r"^\s*>\s?", "", line) for line in stem.splitlines()).strip()
    if not stem:
        raise ValueError(f"{path.name}: empty question stem")

    answer_letters = re.sub(r"[^A-H]", "", answer.upper())
    question_type = "calculation"
    if options:
        question_type = "multi_choice" if len(answer_letters) > 1 else "single_choice"
    tags = [
        _clean_line(str(metadata.get(key) or ""))
        for key in ("module", "topic2", "topic3")
        if _clean_line(str(metadata.get(key) or ""))
    ]
    paper_id = str(metadata.get("paper_id") or "").strip()
    year_match = re.match(r"(19|20)\d{2}", paper_id)
    payload: dict[str, Any] = {
        "question_id": question_id,
        "question_type": question_type,
        "title": stem,
        "options": options,
        "answer": answer,
        "analysis": analysis,
        "sub_questions": [],
        "figures": figures,
        "knowledge_point": knowledge or _clean_line(str(metadata.get("topic3") or "")),
        "tags": list(dict.fromkeys(tags)),
        "source": _clean_line(str(metadata.get("paper_title") or paper_id or "Obsidian 标准题库")),
        "source_raw": str(metadata.get("source_markdown") or path),
        "import_batch_id": "obsidian_vault2_standardized",
        "raw_text": question_body,
        "year": int(year_match.group(0)) if year_match else None,
    }
    return PreparedQuestion(question_id, payload, tuple(Path(item["local_path"]).name for item in figures))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_assets(source_dir: Path, target_dir: Path) -> tuple[int, int]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = skipped = 0
    for source in sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS):
        target = target_dir / source.name
        if target.exists():
            if source.stat().st_size == target.stat().st_size and _sha256(source) == _sha256(target):
                skipped += 1
                continue
            raise ValueError(f"asset name collision with different content: {source.name}")
        shutil.copy2(source, target)
        copied += 1
    return copied, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Obsidian questions for controlled MCP review import.")
    parser.add_argument("--questions-dir", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--start", type=int, default=0, help="Zero-based source-file offset")
    parser.add_argument("--limit", type=int, default=0, help="Maximum source files for this run; 0 means all")
    parser.add_argument("--copy-assets", action="store_true", help="Copy source images after validation")
    parser.add_argument(
        "--allow-missing-images",
        action="store_true",
        help="Keep questions with missing assets, but flag them and omit the broken figure binding",
    )
    args = parser.parse_args()

    if args.chunk_size < 1:
        raise SystemExit("--chunk-size must be positive")
    all_question_files = sorted(
        path
        for path in args.questions_dir.glob("*.md")
        if re.fullmatch(r".*Q\d{8}", path.stem)
    )
    question_files = all_question_files[args.start : args.start + args.limit if args.limit else None]
    if not question_files:
        raise SystemExit(f"No Markdown files found: {args.questions_dir}")
    assets = {path.name for path in args.images_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS}
    prepared = [_prepare_question(path) for path in question_files]
    ids = [question.question_id for question in prepared]
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    if duplicate_ids:
        raise SystemExit(f"Duplicate question IDs: {', '.join(duplicate_ids[:10])}")
    missing = sorted({image for question in prepared for image in question.images if image not in assets})
    if missing and not args.allow_missing_images:
        raise SystemExit(f"Missing referenced images ({len(missing)}): {', '.join(missing[:10])}")
    if missing:
        missing_set = set(missing)
        for question in prepared:
            question_missing = [image for image in question.images if image in missing_set]
            if not question_missing:
                continue
            question.payload["figures"] = [
                figure
                for figure in question.payload["figures"]
                if Path(str(figure.get("local_path") or "")).name not in missing_set
            ]
            question.payload["tags"] = list(dict.fromkeys([*question.payload["tags"], "缺图待补"]))
            question.payload["validation_warnings"] = [
                f"源题引用的图片缺失，未导入图片绑定：{', '.join(question_missing)}"
            ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = args.output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    for index in range(0, len(prepared), args.chunk_size):
        payload = {"questions": [question.payload for question in prepared[index : index + args.chunk_size]]}
        chunk_number = (args.start + index) // args.chunk_size + 1
        (chunks_dir / f"questions-{chunk_number:03d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    copied, skipped = _copy_assets(args.images_dir, args.assets_dir) if args.copy_assets else (0, 0)
    linked_images = sum(len(question.images) for question in prepared)
    manifest = {
        "source_questions_dir": str(args.questions_dir),
        "source_images_dir": str(args.images_dir),
        "asset_target_dir": str(args.assets_dir),
        "question_count": len(prepared),
        "source_question_total": len(all_question_files),
        "start": args.start,
        "asset_count": len(assets),
        "linked_image_count": linked_images,
        "missing_referenced_images": missing,
        "copied_assets": copied,
        "unchanged_assets": skipped,
        "chunk_count": (len(prepared) + args.chunk_size - 1) // args.chunk_size,
        "chunk_size": args.chunk_size,
        "question_ids": ids,
    }
    (args.output_dir / f"manifest-{args.start:05d}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
