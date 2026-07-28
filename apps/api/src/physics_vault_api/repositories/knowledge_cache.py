"""Repository for the knowledge-point generation cache (SQLite).

Stores cached AI-generated content keyed by a deterministic hash of
(sorted knowledge_points, style, length). This avoids repeated MCP
calls for the same knowledge-point combination.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from typing import Any

from ..database import connect_db
from ..paths import default_db_path

logger = logging.getLogger(__name__)

_DB_PATH = default_db_path()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_cache (
    cache_key             TEXT PRIMARY KEY,
    knowledge_points_json TEXT NOT NULL,
    style                 TEXT NOT NULL DEFAULT 'teacher_handout',
    length                TEXT NOT NULL DEFAULT 'medium',
    title                 TEXT NOT NULL DEFAULT '',
    content               TEXT NOT NULL DEFAULT '',
    outline_json          TEXT NOT NULL DEFAULT '[]',
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _resolve_db_path(path: str | None = None) -> str:
    return path or str(_DB_PATH)


class KnowledgeCacheRepository:
    """Data access for the knowledge-point generation cache."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    def _ensure_table(self) -> None:
        try:
            with closing(self._get_connection()) as conn:
                conn.execute(CREATE_TABLE_SQL)
                conn.commit()
        except Exception:
            logger.exception("Failed to ensure knowledge_cache table")

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return dict(row) if row else None

    def upsert(self, entry: dict[str, Any]) -> None:
        with closing(self._get_connection()) as conn:
            conn.execute(
                """
                INSERT INTO knowledge_cache (
                    cache_key, knowledge_points_json, style, length,
                    title, content, outline_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(cache_key) DO UPDATE SET
                    knowledge_points_json = excluded.knowledge_points_json,
                    style = excluded.style,
                    length = excluded.length,
                    title = excluded.title,
                    content = excluded.content,
                    outline_json = excluded.outline_json,
                    updated_at = datetime('now')
                """,
                (
                    entry["cache_key"],
                    entry["knowledge_points_json"],
                    entry.get("style", "teacher_handout"),
                    entry.get("length", "medium"),
                    entry.get("title", ""),
                    entry.get("content", ""),
                    entry.get("outline_json", "[]"),
                ),
            )
            conn.commit()

    def delete(self, cache_key: str) -> bool:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute(
                "DELETE FROM knowledge_cache WHERE cache_key = ?",
                (cache_key,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_all(self) -> int:
        with closing(self._get_connection()) as conn:
            cursor = conn.execute("DELETE FROM knowledge_cache")
            conn.commit()
            return cursor.rowcount
