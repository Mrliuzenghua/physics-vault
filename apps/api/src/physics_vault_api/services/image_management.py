"""Service for question image management — add/replace/delete/reorder/validate."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path

from ..schemas.image_management import (
    AddImageRequest,
    ImageListResponse,
    PlaceholderIssue,
    QuestionImageDetail,
    ReorderRequest,
    ReplaceImageRequest,
    UpdateImageRequest,
    ValidationResponse,
)

logger = logging.getLogger(__name__)


class ImageManagementService:
    """Manages question-image bindings in question_assets + image_assets tables."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else default_db_path()

    def _db_available(self) -> bool:
        return self._db_path.exists()

    def _get_connection(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    # ── List ────────────────────────────────────────────────────

    def list_images(self, question_id: str) -> ImageListResponse:
        if not self._db_available():
            return ImageListResponse(question_id=question_id)

        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT qa.link_id, qa.asset_id, qa.role, qa.sort_order,
                       qa.placeholder_key, qa.display_scale, qa.is_primary, qa.is_verified,
                       ia.filename, ia.file_path, ia.mime_type, ia.width, ia.height,
                       ia.description
                FROM question_assets qa
                INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
                WHERE qa.question_id = ?
                ORDER BY qa.sort_order, qa.asset_id
                """,
                (question_id,),
            ).fetchall()

            stem = conn.execute(
                "SELECT stem_text, figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()

        images = [self._normalize_image(dict(r)) for r in rows]
        known_refs = {image.asset_id for image in images} | {
            image.placeholder_key for image in images if image.placeholder_key
        }
        figures = self._decode_figures(stem["figures_json"] if stem else None)
        for index, figure in enumerate(figures, start=len(images)):
            figure_id = str(figure.get("fig_uuid") or "").strip()
            local_path = str(figure.get("local_path") or "").strip()
            if not figure_id or figure_id in known_refs:
                continue
            images.append(QuestionImageDetail(
                link_id=f"{question_id}-{figure_id}",
                asset_id=figure_id,
                filename=Path(local_path).name or figure_id,
                file_path=local_path,
                role=str(figure.get("role") or "stem"),
                sort_order=index,
                placeholder_key=figure_id,
                display_scale=float(figure.get("display_scale") or 60),
                is_primary=index == 0,
            ))

        return ImageListResponse(
            question_id=question_id,
            images=images,
            stem_text=stem["stem_text"] if stem else "",
        )

    @staticmethod
    def _normalize_image(d: dict) -> QuestionImageDetail:
        """Strip vault-relative path prefixes so file_path is project-root-relative."""
        fp = d.get("file_path") or ""
        for prefix in ("09-项目工程/physics-vault/", "physics-vault/"):
            if fp.startswith(prefix):
                d["file_path"] = fp[len(prefix):]
                break
        return QuestionImageDetail(**d)

    @staticmethod
    def _decode_figures(raw: str | None) -> list[dict[str, Any]]:
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _write_figures(conn: sqlite3.Connection, question_id: str, figures: list[dict[str, Any]], stem_text: str | None = None) -> None:
        if stem_text is None:
            conn.execute(
                "UPDATE question_text_index SET figures_json = ? WHERE question_id = ?",
                (json.dumps(figures, ensure_ascii=False), question_id),
            )
        else:
            conn.execute(
                "UPDATE question_text_index SET figures_json = ?, stem_text = ? WHERE question_id = ?",
                (json.dumps(figures, ensure_ascii=False), stem_text, question_id),
            )

    # ── Add ─────────────────────────────────────────────────────

    def add_image(self, question_id: str, req: AddImageRequest) -> QuestionImageDetail:
        with closing(self._get_connection()) as conn:
            # Verify asset exists
            img = conn.execute(
                "SELECT asset_id, filename, file_path, mime_type, width, height FROM image_assets WHERE asset_id = ?",
                (req.asset_id,),
            ).fetchone()
            if img is None:
                raise ValueError(f"素材不存在: {req.asset_id}")

            # Determine sort_order
            if req.sort_order is not None:
                order = req.sort_order
            else:
                max_o = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM question_assets WHERE question_id = ?",
                    (question_id,),
                ).fetchone()[0]
                order = max_o

            link_id = f"{question_id}-{req.asset_id}"

            conn.execute(
                """
            INSERT OR REPLACE INTO question_assets
                    (link_id, question_id, asset_id, role, sort_order, placeholder_key, display_scale, is_primary, is_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 60, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (link_id, question_id, req.asset_id, req.role, order, req.placeholder_key, int(req.is_primary)),
            )
            figure_id = req.placeholder_key or req.asset_id
            text_row = conn.execute(
                "SELECT stem_text, figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if text_row:
                figures = self._decode_figures(text_row["figures_json"])
                if not any(str(figure.get("fig_uuid")) == figure_id for figure in figures):
                    figures.append({
                        "fig_uuid": figure_id,
                        "local_path": img["file_path"],
                        "role": req.role,
                        "display_scale": 60,
                    })
                stem_text = str(text_row["stem_text"] or "")
                placeholder = f"![fig:{figure_id}]"
                if placeholder not in stem_text:
                    stem_text = f"{stem_text.rstrip()}\n\n{placeholder}".strip()
                self._write_figures(conn, question_id, figures, stem_text)
            conn.commit()

        return QuestionImageDetail(
            link_id=link_id,
            asset_id=req.asset_id,
            filename=img["filename"],
            file_path=img["file_path"],
            role=req.role,
            sort_order=order,
            placeholder_key=req.placeholder_key,
            display_scale=60,
            is_primary=req.is_primary,
            mime_type=img["mime_type"],
            width=img["width"],
            height=img["height"],
        )

    # ── Replace ─────────────────────────────────────────────────

    def replace_image(self, question_id: str, req: ReplaceImageRequest) -> QuestionImageDetail:
        with closing(self._get_connection()) as conn:
            old = conn.execute(
                "SELECT * FROM question_assets WHERE question_id = ? AND asset_id = ?",
                (question_id, req.old_asset_id),
            ).fetchone()
            new_img = conn.execute(
                "SELECT asset_id, filename, file_path, mime_type, width, height FROM image_assets WHERE asset_id = ?",
                (req.new_asset_id,),
            ).fetchone()
            if new_img is None:
                raise ValueError(f"新素材不存在: {req.new_asset_id}")

            if old is None:
                text_row = conn.execute(
                    "SELECT figures_json FROM question_text_index WHERE question_id = ?",
                    (question_id,),
                ).fetchone()
                figures = self._decode_figures(text_row["figures_json"] if text_row else None)
                legacy = next((figure for figure in figures if str(figure.get("fig_uuid")) == req.old_asset_id), None)
                if legacy is None:
                    raise ValueError(f"当前绑定不存在: {req.old_asset_id}")
                legacy["local_path"] = new_img["file_path"]
                self._write_figures(conn, question_id, figures)
                conn.commit()
                return QuestionImageDetail(
                    link_id=f"{question_id}-{req.old_asset_id}",
                    asset_id=req.old_asset_id,
                    filename=new_img["filename"],
                    file_path=new_img["file_path"],
                    role=str(legacy.get("role") or "stem"),
                    sort_order=figures.index(legacy),
                    placeholder_key=req.old_asset_id,
                    display_scale=float(legacy.get("display_scale") or 60),
                    is_primary=figures.index(legacy) == 0,
                    mime_type=new_img["mime_type"],
                    width=new_img["width"],
                    height=new_img["height"],
                )

            # Delete old binding, insert new with same metadata
            conn.execute(
                "DELETE FROM question_assets WHERE question_id = ? AND asset_id = ?",
                (question_id, req.old_asset_id),
            )
            new_link = f"{question_id}-{req.new_asset_id}"
            conn.execute(
                """
                INSERT INTO question_assets
                    (link_id, question_id, asset_id, role, sort_order, placeholder_key, display_scale, is_primary, is_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (new_link, question_id, req.new_asset_id, old["role"], old["sort_order"], old["placeholder_key"], old["display_scale"], old["is_primary"]),
            )
            text_row = conn.execute(
                "SELECT figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            figures = self._decode_figures(text_row["figures_json"] if text_row else None)
            figure_ref = old["placeholder_key"] or req.old_asset_id
            for figure in figures:
                if str(figure.get("fig_uuid")) == figure_ref:
                    figure["local_path"] = new_img["file_path"]
            self._write_figures(conn, question_id, figures)
            conn.commit()

        return QuestionImageDetail(
            link_id=new_link,
            asset_id=req.new_asset_id,
            filename=new_img["filename"],
            file_path=new_img["file_path"],
            role=old["role"],
            sort_order=old["sort_order"],
            placeholder_key=old["placeholder_key"],
            display_scale=old["display_scale"],
            is_primary=bool(old["is_primary"]),
            mime_type=new_img["mime_type"],
            width=new_img["width"],
            height=new_img["height"],
        )

    # ── Update metadata ─────────────────────────────────────────

    def update_image(self, question_id: str, asset_id: str, req: UpdateImageRequest) -> bool:
        with closing(self._get_connection()) as conn:
            parts = []
            params: list[Any] = []
            for field in ("role", "sort_order", "placeholder_key", "display_scale", "is_primary"):
                val = getattr(req, field, None)
                if val is not None:
                    parts.append(f"{field} = ?")
                    params.append(int(val) if field == "is_primary" else val)
            if req.description is not None:
                # description lives in image_assets
                conn.execute(
                    "UPDATE image_assets SET description = ? WHERE asset_id = ?",
                    (req.description, asset_id),
                )
            if not parts:
                return False
            params.append(question_id)
            params.append(asset_id)
            conn.execute(
                f"UPDATE question_assets SET {', '.join(parts)}, updated_at = CURRENT_TIMESTAMP WHERE question_id = ? AND asset_id = ?",
                params,
            )
            row = conn.execute(
                "SELECT stem_text, figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row:
                figures = self._decode_figures(row["figures_json"])
                stem_text = str(row["stem_text"] or "")
                for figure in figures:
                    if str(figure.get("fig_uuid")) != asset_id:
                        continue
                    if req.display_scale is not None:
                        figure["display_scale"] = req.display_scale
                    if req.role is not None:
                        figure["role"] = req.role
                    if req.placeholder_key:
                        figure["fig_uuid"] = req.placeholder_key
                        stem_text = stem_text.replace(f"![fig:{asset_id}]", f"![fig:{req.placeholder_key}]")
                self._write_figures(conn, question_id, figures, stem_text)
            conn.commit()
        return True

    # ── Delete ──────────────────────────────────────────────────

    def delete_image(self, question_id: str, asset_id: str) -> bool:
        with closing(self._get_connection()) as conn:
            binding = conn.execute(
                "SELECT placeholder_key FROM question_assets WHERE question_id = ? AND asset_id = ?",
                (question_id, asset_id),
            ).fetchone()
            cur = conn.execute(
                "DELETE FROM question_assets WHERE question_id = ? AND asset_id = ?",
                (question_id, asset_id),
            )
            row = conn.execute(
                "SELECT stem_text, figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            removed_legacy = False
            if row:
                figure_ref = str(binding["placeholder_key"] if binding and binding["placeholder_key"] else asset_id)
                figures = self._decode_figures(row["figures_json"])
                next_figures = [figure for figure in figures if str(figure.get("fig_uuid")) != figure_ref]
                removed_legacy = len(next_figures) != len(figures)
                stem_text = str(row["stem_text"] or "").replace(f"![fig:{figure_ref}]", "")
                stem_text = re.sub(r"\n{3,}", "\n\n", stem_text).strip()
                self._write_figures(conn, question_id, next_figures, stem_text)
            conn.commit()
            return cur.rowcount > 0 or removed_legacy

    # ── Reorder ─────────────────────────────────────────────────

    def reorder_images(self, question_id: str, req: ReorderRequest) -> None:
        with closing(self._get_connection()) as conn:
            for idx, aid in enumerate(req.asset_ids):
                conn.execute(
                    "UPDATE question_assets SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ? AND asset_id = ?",
                    (idx, question_id, aid),
                )
            row = conn.execute(
                "SELECT figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row:
                figures = self._decode_figures(row["figures_json"])
                order = {asset_id: index for index, asset_id in enumerate(req.asset_ids)}
                figures.sort(key=lambda figure: order.get(str(figure.get("fig_uuid")), len(order)))
                self._write_figures(conn, question_id, figures)
            conn.commit()

    # ── Validate ────────────────────────────────────────────────

    def validate(self, question_id: str) -> ValidationResponse:
        if not self._db_available():
            return ValidationResponse(valid=False, issues=[PlaceholderIssue(type="error", message="数据库不可用")])

        with closing(self._get_connection()) as conn:
            stem_row = conn.execute(
                "SELECT stem_text, figures_json FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            stem = stem_row["stem_text"] if stem_row else ""
            legacy_figures = self._decode_figures(stem_row["figures_json"] if stem_row else None)

            rows = conn.execute(
                "SELECT placeholder_key, asset_id FROM question_assets WHERE question_id = ?",
                (question_id,),
            ).fetchall()

        issues: list[PlaceholderIssue] = []

        # Find all placeholder refs in stem
        refs = set(re.findall(r"!\[fig:([^\]]+)\]", stem))
        bound_placeholders = {r["placeholder_key"] for r in rows if r["placeholder_key"]}
        bound_placeholders.update(
            str(figure.get("fig_uuid")) for figure in legacy_figures if figure.get("fig_uuid")
        )

        # Check duplicate placeholders
        placeholder_counts: dict[str, int] = {}
        for r in rows:
            if r["placeholder_key"]:
                placeholder_counts[r["placeholder_key"]] = placeholder_counts.get(r["placeholder_key"], 0) + 1
        for key, cnt in placeholder_counts.items():
            if cnt > 1:
                issues.append(PlaceholderIssue(type="duplicate_placeholder", message=f"占位符 {key} 重复绑定 {cnt} 次", fig_uuid=key))

        # Missing images: stem refs a placeholder with no binding
        for ref in refs:
            if ref not in bound_placeholders:
                issues.append(PlaceholderIssue(type="missing_image", message=f"题干引用 {ref} 无对应图片绑定", fig_uuid=ref))

        # Unreferenced images: binding without stem ref
        for key in bound_placeholders:
            if key and key not in refs:
                issues.append(PlaceholderIssue(type="unreferenced_image", message=f"图片 {key} 未被题干引用", fig_uuid=key))

        # Images without placeholder_key at all
        for r in rows:
            if not r["placeholder_key"]:
                issues.append(PlaceholderIssue(type="unreferenced_image", message=f"素材 {r['asset_id']} 未绑定占位符", fig_uuid=None))

        return ValidationResponse(valid=len(issues) == 0, issues=issues)

    # ── Available images (for picker) ──────────────────────────

    def available_images(self, keyword: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if not self._db_available():
            return []
        with closing(self._get_connection()) as conn:
            if keyword:
                rows = conn.execute(
                    "SELECT asset_id, filename, file_path, mime_type FROM image_assets WHERE filename LIKE ? OR file_path LIKE ? LIMIT ?",
                    (f"%{keyword}%", f"%{keyword}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT asset_id, filename, file_path, mime_type FROM image_assets ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]
