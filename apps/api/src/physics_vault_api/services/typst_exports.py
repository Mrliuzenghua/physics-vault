"""Read-only canonical-question data export for user-owned Typst templates."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..database import connect_db
from ..paths import default_db_path, default_exports_dir, project_root

_MAX_QUESTIONS_PER_EXPORT = 50
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}


class TypstExportError(ValueError):
    """A safe, user-facing error for an invalid Typst export request."""


class TypstQuestionExportService:
    """Export template-neutral Typst data without modifying the question or image stores."""

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        export_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path else default_db_path()
        self._export_dir = (export_dir or default_exports_dir()).resolve()
        self._project_dir = (project_dir or project_root()).resolve()

    def export(
        self,
        question_ids: list[str],
        *,
        title: str | None = None,
        include_answers: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        normalized_ids = list(dict.fromkeys(str(item).strip() for item in question_ids if str(item).strip()))
        if not normalized_ids:
            raise TypstExportError("question_ids 至少需要一个有效题号。")
        if len(normalized_ids) > _MAX_QUESTIONS_PER_EXPORT:
            raise TypstExportError(f"一次最多导出 {_MAX_QUESTIONS_PER_EXPORT} 道题。")

        questions = self._load_questions(normalized_ids)
        found_ids = {str(question["question_id"]) for question in questions}
        missing_question_ids = [question_id for question_id in normalized_ids if question_id not in found_ids]
        export_id = f"typst-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        output_dir = self._export_dir / "typst" / export_id
        image_map, image_manifest, unavailable_images = self._resolve_images(questions, output_dir)
        bundle_title = (title or "物理题目学案").strip() or "物理题目学案"
        planned_files = ["questions-data.typ", "image-map.typ"]
        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=False)
            (output_dir / "questions-data.typ").write_text(
                self._render_question_data(bundle_title, questions, include_answers),
                encoding="utf-8",
            )
            (output_dir / "image-map.typ").write_text(
                self._render_image_map(image_map),
                encoding="utf-8",
            )

        return {
            "ok": True,
            "dry_run": dry_run,
            "export_id": export_id,
            "output_dir": str(output_dir),
            "planned_files": planned_files,
            "question_count": len(questions),
            "missing_question_ids": missing_question_ids,
            "referenced_image_count": len(image_manifest),
            "unavailable_images": unavailable_images,
            "gallery_policy": "read_only_reference_no_copy_move_rename_or_delete",
            "images": image_manifest,
            "next_step": (
                "预览已完成；确认后以 dry_run=false 再次调用，系统只会创建独立 Typst 数据导出目录。"
                if dry_run
                else "在你的讲义模板中 import questions-data.typ 与 image-map.typ；图片仍引用原图库，未复制或修改图库文件。"
            ),
        }

    def _load_questions(self, question_ids: list[str]) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in question_ids)
        order_case = "CASE q.question_id " + " ".join(
            f"WHEN ? THEN {index}" for index, _ in enumerate(question_ids)
        ) + " END"
        with closing(connect_db(self._db_path, writable=False)) as connection:
            rows = connection.execute(
                f"""
                SELECT q.question_id, q.canonical_title, q.question_type,
                       qti.title_text, qti.stem_text, qti.options_json, qti.figures_json,
                       qti.answer_text, qti.analysis_text
                FROM questions q
                LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
                WHERE q.question_id IN ({placeholders})
                ORDER BY {order_case}
                """,
                question_ids + question_ids,
            ).fetchall()
            questions = [dict(row) for row in rows]
            assets_by_question = self._load_question_assets(connection, [question["question_id"] for question in questions])
        for question in questions:
            question["assets"] = assets_by_question.get(str(question["question_id"]), []) or self._legacy_figure_assets(question)
        return questions

    @staticmethod
    def _load_question_assets(
        connection: sqlite3.Connection,
        question_ids: list[str],
    ) -> dict[str, list[dict[str, str]]]:
        if not question_ids:
            return {}
        required_tables = {"image_assets", "question_assets"}
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('image_assets', 'question_assets')"
        ).fetchall()
        if {str(row["name"]) for row in table_rows} != required_tables:
            return {}
        placeholders = ",".join("?" for _ in question_ids)
        rows = connection.execute(
            f"""
            SELECT * FROM (
                SELECT qa.question_id, qa.asset_id, ia.filename, ia.file_path, qa.sort_order
                FROM question_assets qa
                INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
                WHERE qa.question_id IN ({placeholders})
                UNION ALL
                SELECT ia.question_id, ia.asset_id, ia.filename, ia.file_path, 0 AS sort_order
                FROM image_assets ia
                WHERE ia.question_id IN ({placeholders})
                  AND NOT EXISTS (
                      SELECT 1 FROM question_assets qa WHERE qa.question_id = ia.question_id
                  )
            )
            ORDER BY question_id, sort_order, asset_id
            """,
            question_ids + question_ids,
        ).fetchall()
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault(str(row["question_id"]), []).append(
                {
                    "asset_id": str(row["asset_id"]),
                    "filename": str(row["filename"]),
                    "file_path": str(row["file_path"]),
                }
            )
        return grouped

    @staticmethod
    def _legacy_figure_assets(question: dict[str, Any]) -> list[dict[str, str]]:
        try:
            figures = json.loads(question.get("figures_json") or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(figures, list):
            return []
        assets: list[dict[str, str]] = []
        for index, figure in enumerate(figures, start=1):
            if not isinstance(figure, dict):
                continue
            file_path = str(figure.get("local_path") or figure.get("file_path") or figure.get("path") or "")
            if not file_path:
                continue
            assets.append(
                {
                    "asset_id": str(figure.get("asset_id") or figure.get("fig_uuid") or f"legacy-figure-{index}"),
                    "filename": Path(file_path).name,
                    "file_path": file_path,
                }
            )
        return assets

    def _resolve_images(
        self,
        questions: list[dict[str, Any]],
        output_dir: Path,
    ) -> tuple[dict[str, list[str]], list[dict[str, str]], list[dict[str, str]]]:
        image_map: dict[str, list[str]] = {}
        manifest: list[dict[str, str]] = []
        unavailable: list[dict[str, str]] = []
        for question in questions:
            question_id = str(question["question_id"])
            for asset in question["assets"]:
                source = self._resolve_managed_image_path(asset["file_path"])
                if source is None:
                    unavailable.append(
                        {
                            "question_id": question_id,
                            "asset_id": asset["asset_id"],
                            "reason": "图片不存在、格式不受支持，或不在受管图库目录。",
                        }
                    )
                    continue
                relative_path = Path(os.path.relpath(source, output_dir)).as_posix()
                image_map.setdefault(question_id, []).append(relative_path)
                manifest.append(
                    {
                        "question_id": question_id,
                        "asset_id": asset["asset_id"],
                        "source_path": str(source),
                        "typst_relative_path": relative_path,
                    }
                )
        return image_map, manifest, unavailable

    def _resolve_managed_image_path(self, raw_path: str) -> Path | None:
        candidate = Path(str(raw_path or "").strip()).expanduser()
        if not candidate:
            return None
        target = candidate.resolve() if candidate.is_absolute() else (self._project_dir / candidate).resolve()
        managed_roots = (
            (self._project_dir / "data" / "assets").resolve(),
            (self._project_dir / "data" / "import-batches").resolve(),
        )
        if not target.is_file() or target.suffix.lower() not in _IMAGE_SUFFIXES:
            return None
        return target if any(target == root or root in target.parents for root in managed_roots) else None

    @staticmethod
    def _typst_string(value: Any) -> str:
        text = str(value or "")
        return json.dumps(text, ensure_ascii=False)

    @classmethod
    def _typst_options_data(cls, raw: str | None) -> str:
        try:
            values = json.loads(raw or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            values = []
        if not isinstance(values, list):
            return "()"
        options: list[str] = []
        for index, value in enumerate(values):
            if isinstance(value, dict):
                label = str(value.get("label") or chr(ord("A") + index))
                text = str(value.get("text") or value.get("content") or "")
            else:
                label = chr(ord("A") + index)
                text = str(value)
            options.append(f"(label: {cls._typst_string(label)}, text: {cls._typst_string(text)})")
        return "(" + ", ".join(options) + ("," if options else "") + ")"

    def _render_question_data(
        self,
        title: str,
        questions: list[dict[str, Any]],
        include_answers: bool,
    ) -> str:
        lines = [
            "// Generated by Physics Vault. This file contains data only; it defines no layout or visual style.",
            f"#let export-meta = (title: {self._typst_string(title)}, include_answers: {'true' if include_answers else 'false'})",
            "",
            "#let question-data = (",
        ]
        for question in questions:
            question_id = str(question["question_id"])
            title_text = question.get("title_text") or question.get("canonical_title")
            title_value = self._typst_string(title_text) if title_text else '""'
            answer = self._typst_string(question.get("answer_text")) if include_answers and question.get("answer_text") else "none"
            analysis = self._typst_string(question.get("analysis_text")) if include_answers and question.get("analysis_text") else "none"
            lines.extend(
                [
                    "  (",
                    f"    question_id: {self._typst_string(question_id)},",
                    f"    title: {title_value},",
                    f"    question_type: {self._typst_string(question.get('question_type'))},",
                    f"    stem: {self._typst_string(question.get('stem_text'))},",
                    f"    options: {self._typst_options_data(question.get('options_json'))},",
                    f"    answer: {answer},",
                    f"    analysis: {analysis},",
                    "  ),",
                ]
            )
        lines.extend(
            [
                ")",
                "",
            ]
        )
        return "\n".join(lines)

    def _render_image_map(self, image_map: dict[str, list[str]]) -> str:
        entries = []
        for question_id, paths in image_map.items():
            rendered_paths = ", ".join(self._typst_string(path) for path in paths)
            entries.append(f"  {self._typst_string(question_id)}: ({rendered_paths},),")
        return "\n".join(
            [
                "// Generated by Physics Vault. This file contains image paths only; it applies no figure style.",
                "#let figure-paths = (",
                *entries,
                ")",
                "#let figures-for(question_id) = figure-paths.at(question_id, default: ())",
                "",
            ]
        )
