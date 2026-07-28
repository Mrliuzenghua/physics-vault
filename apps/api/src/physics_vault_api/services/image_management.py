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
                       qa.placeholder_key, qa.is_primary, qa.is_verified,
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
                "SELECT stem_text FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()

        return ImageListResponse(
            question_id=question_id,
            images=[self._normalize_image(dict(r)) for r in rows],
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
                    (link_id, question_id, asset_id, role, sort_order, placeholder_key, is_primary, is_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (link_id, question_id, req.asset_id, req.role, order, req.placeholder_key, int(req.is_primary)),
            )
            conn.commit()

        return QuestionImageDetail(
            link_id=link_id,
            asset_id=req.asset_id,
            filename=img["filename"],
            file_path=img["file_path"],
            role=req.role,
            sort_order=order,
            placeholder_key=req.placeholder_key,
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
            if old is None:
                raise ValueError(f"当前绑定不存在: {req.old_asset_id}")

            new_img = conn.execute(
                "SELECT asset_id, filename, file_path, mime_type, width, height FROM image_assets WHERE asset_id = ?",
                (req.new_asset_id,),
            ).fetchone()
            if new_img is None:
                raise ValueError(f"新素材不存在: {req.new_asset_id}")

            # Delete old binding, insert new with same metadata
            conn.execute(
                "DELETE FROM question_assets WHERE question_id = ? AND asset_id = ?",
                (question_id, req.old_asset_id),
            )
            new_link = f"{question_id}-{req.new_asset_id}"
            conn.execute(
                """
                INSERT INTO question_assets
                    (link_id, question_id, asset_id, role, sort_order, placeholder_key, is_primary, is_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (new_link, question_id, req.new_asset_id, old["role"], old["sort_order"], old["placeholder_key"], old["is_primary"]),
            )
            conn.commit()

        return QuestionImageDetail(
            link_id=new_link,
            asset_id=req.new_asset_id,
            filename=new_img["filename"],
            file_path=new_img["file_path"],
            role=old["role"],
            sort_order=old["sort_order"],
            placeholder_key=old["placeholder_key"],
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
            for field in ("role", "sort_order", "placeholder_key", "is_primary"):
                val = getattr(req, field, None)
                if val is not None:
                    parts.append(f"{field} = ?")
                    params.append(int(val) if field == "is_primary" else val)
            if req.description is not None:
                # description lives in image_assets
                conn.execute(
                    "UPDATE image_assets SET description = ? WHERE asset_id = ?",
                    (req.description, req.description),
                )
            if not parts:
                return False
            params.append(question_id)
            params.append(asset_id)
            conn.execute(
                f"UPDATE question_assets SET {', '.join(parts)}, updated_at = CURRENT_TIMESTAMP WHERE question_id = ? AND asset_id = ?",
                params,
            )
            conn.commit()
        return True

    # ── Delete ──────────────────────────────────────────────────

    def delete_image(self, question_id: str, asset_id: str) -> bool:
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                "DELETE FROM question_assets WHERE question_id = ? AND asset_id = ?",
                (question_id, asset_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Reorder ─────────────────────────────────────────────────

    def reorder_images(self, question_id: str, req: ReorderRequest) -> None:
        with closing(self._get_connection()) as conn:
            for idx, aid in enumerate(req.asset_ids):
                conn.execute(
                    "UPDATE question_assets SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ? AND asset_id = ?",
                    (idx, question_id, aid),
                )
            conn.commit()

    # ── Validate ────────────────────────────────────────────────

    def validate(self, question_id: str) -> ValidationResponse:
        if not self._db_available():
            return ValidationResponse(valid=False, issues=[PlaceholderIssue(type="error", message="数据库不可用")])

        with closing(self._get_connection()) as conn:
            stem_row = conn.execute(
                "SELECT stem_text FROM question_text_index WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            stem = stem_row["stem_text"] if stem_row else ""

            rows = conn.execute(
                "SELECT placeholder_key, asset_id FROM question_assets WHERE question_id = ?",
                (question_id,),
            ).fetchall()

        issues: list[PlaceholderIssue] = []

        # Find all placeholder refs in stem
        refs = set(re.findall(r"!\[fig:([^\]]+)\]", stem))
        bound_placeholders = {r["placeholder_key"] for r in rows if r["placeholder_key"]}
        bound_asset_ids = {r["asset_id"] for r in rows}
        all_keys = refs | bound_placeholders

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
