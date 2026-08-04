"""Repository for question annotations (批注) stored in SQLite."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..database import connect_db
from ..paths import default_db_path

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS question_annotations (
    annotation_id   TEXT PRIMARY KEY,
    question_id     TEXT NOT NULL,
    annotation_type TEXT NOT NULL DEFAULT 'text',
    content         TEXT NOT NULL DEFAULT '',
    anchor_start    INTEGER,
    anchor_end      INTEGER,
    anchor_text     TEXT,
    figure_uuid     TEXT,
    color           TEXT DEFAULT '#fbbf24',
    author          TEXT DEFAULT '教师',
    visibility      TEXT NOT NULL DEFAULT 'private',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_annot_qid
ON question_annotations(question_id)
"""


def _resolve_db_path(path: str | None = None) -> str:
    return path or str(default_db_path())


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


class AnnotationRepository:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    def _ensure_table(self) -> None:
        try:
            with closing(self._get_connection()) as conn:
                conn.execute(CREATE_TABLE_SQL)
                conn.execute(CREATE_INDEX_SQL)
                conn.commit()
        except Exception:
            logger.exception("Failed to ensure question_annotations table")

    def list_by_question(self, question_id: str) -> list[dict[str, Any]]:
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM question_annotations
                WHERE question_id = ?
                ORDER BY created_at ASC
                """,
                (question_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, annotation_id: str) -> dict[str, Any] | None:
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                "SELECT * FROM question_annotations WHERE annotation_id = ?",
                (annotation_id,),
            ).fetchone()
        return dict(row) if row else None

    def create(self, entry: dict[str, Any]) -> dict[str, Any]:
        annotation_id = entry.get("annotation_id") or str(uuid4())
        now = _utc_now()
        with closing(self._get_connection()) as conn:
            conn.execute(
                """
                INSERT INTO question_annotations (
                    annotation_id, question_id, annotation_type, content,
                    anchor_start, anchor_end, anchor_text, figure_uuid,
                    color, author, visibility, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id,
                    entry["question_id"],
                    entry.get("annotation_type", "text"),
                    entry.get("content", ""),
                    entry.get("anchor_start"),
                    entry.get("anchor_end"),
                    entry.get("anchor_text"),
                    entry.get("figure_uuid"),
                    entry.get("color", "#fbbf24"),
                    entry.get("author", "教师"),
                    entry.get("visibility", "private"),
                    now,
                    now,
                ),
            )
            conn.commit()
        return self.get(annotation_id) or {}

    def update(self, annotation_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get(annotation_id)
        if not existing:
            return None

        merged = {**existing, **patch, "updated_at": _utc_now()}
        with closing(self._get_connection()) as conn:
            conn.execute(
                """
                UPDATE question_annotations
                SET annotation_type = ?, content = ?, anchor_start = ?, anchor_end = ?,
                    anchor_text = ?, figure_uuid = ?, color = ?, author = ?,
                    visibility = ?, updated_at = ?
                WHERE annotation_id = ?
                """,
                (
                    merged["annotation_type"],
                    merged["content"],
                    merged.get("anchor_start"),
                    merged.get("anchor_end"),
                    merged.get("anchor_text"),
                    merged.get("figure_uuid"),
                    merged.get("color", "#fbbf24"),
                    merged.get("author", "教师"),
                    merged.get("visibility", "private"),
                    merged["updated_at"],
                    annotation_id,
                ),
            )
            conn.commit()
        return self.get(annotation_id)

    def delete(self, annotation_id: str) -> bool:
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                "DELETE FROM question_annotations WHERE annotation_id = ?",
                (annotation_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_by_question(self, question_id: str) -> int:
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                "DELETE FROM question_annotations WHERE question_id = ?",
                (question_id,),
            )
            conn.commit()
            return cur.rowcount
