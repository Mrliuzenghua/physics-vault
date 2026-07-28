"""Repository for collections and question-collection mappings (SQLite)."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import closing
from typing import Any

from ..database import connect_db
from ..paths import default_db_path

logger = logging.getLogger(__name__)

_DB_PATH = default_db_path()

CREATE_COLLECTIONS = """
CREATE TABLE IF NOT EXISTS collections (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    parent_id   TEXT,
    type        TEXT NOT NULL DEFAULT 'directory',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES collections(id) ON DELETE SET NULL
)
"""

CREATE_COLLECTION_QUESTIONS = """
CREATE TABLE IF NOT EXISTS collection_questions (
    collection_id TEXT NOT NULL,
    question_id   TEXT NOT NULL,
    added_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (collection_id, question_id),
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
)
"""


def _resolve_db_path(path: str | None = None) -> str:
    return path or str(_DB_PATH)


class CollectionsRepository:
    """Data access for collections and question-collection mappings."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    def _ensure_tables(self) -> None:
        try:
            with closing(self._get_connection()) as conn:
                conn.execute(CREATE_COLLECTIONS)
                conn.execute(CREATE_COLLECTION_QUESTIONS)
                conn.commit()
        except Exception:
            logger.exception("Failed to create collection tables")

    def list_all(self) -> list[dict[str, Any]]:
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT c.*, COALESCE(cq.cnt, 0) AS question_count
                FROM collections c
                LEFT JOIN (
                    SELECT collection_id, COUNT(*) AS cnt
                    FROM collection_questions
                    GROUP BY collection_id
                ) cq ON cq.collection_id = c.id
                ORDER BY c.type, c.name
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, collection_id: str) -> dict[str, Any] | None:
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                "SELECT * FROM collections WHERE id = ?",
                (collection_id,),
            ).fetchone()
        return dict(row) if row else None

    def create(self, name: str, parent_id: str | None, ctype: str) -> dict[str, Any]:
        coll_id = f"COL-{uuid.uuid4().hex[:12]}"
        with closing(self._get_connection()) as conn:
            conn.execute(
                """
                INSERT INTO collections (id, name, parent_id, type)
                VALUES (?, ?, ?, ?)
                """,
                (coll_id, name, parent_id, ctype),
            )
            conn.commit()
        return {"id": coll_id, "name": name, "parent_id": parent_id, "type": ctype}

    def delete(self, collection_id: str) -> bool:
        with closing(self._get_connection()) as conn:
            conn.execute(
                "DELETE FROM collection_questions WHERE collection_id = ?",
                (collection_id,),
            )
            cur = conn.execute(
                "DELETE FROM collections WHERE id = ?",
                (collection_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def add_questions(self, collection_id: str, question_ids: list[str]) -> dict[str, Any]:
        success = 0
        skipped = 0
        failed = 0
        results: list[dict[str, Any]] = []

        with closing(self._get_connection()) as conn:
            for qid in question_ids:
                try:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO collection_questions (collection_id, question_id)
                        VALUES (?, ?)
                        """,
                        (collection_id, qid),
                    )
                    if cur.rowcount > 0:
                        success += 1
                        results.append({"question_id": qid, "status": "success", "message": "added"})
                    else:
                        skipped += 1
                        results.append({"question_id": qid, "status": "skipped", "message": "exists"})
                except Exception as exc:
                    failed += 1
                    results.append({"question_id": qid, "status": "failed", "message": str(exc)})
            conn.commit()

        return {
            "total": len(question_ids),
            "success_count": success,
            "skipped_count": skipped,
            "failed_count": failed,
            "results": results,
        }

    def remove_questions(self, collection_id: str, question_ids: list[str]) -> int:
        if not question_ids:
            return 0
        placeholders = ",".join("?" for _ in question_ids)
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                f"""
                DELETE FROM collection_questions
                WHERE collection_id = ? AND question_id IN ({placeholders})
                """,
                [collection_id] + question_ids,
            )
            conn.commit()
            return cur.rowcount

    def get_questions(self, collection_id: str) -> list[str]:
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                "SELECT question_id FROM collection_questions WHERE collection_id = ?",
                (collection_id,),
            ).fetchall()
        return [r["question_id"] for r in rows]

    def get_collections_for_question(self, question_id: str) -> list[dict[str, Any]]:
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT c.*
                FROM collections c
                INNER JOIN collection_questions cq ON cq.collection_id = c.id
                WHERE cq.question_id = ?
                ORDER BY c.type, c.name
                """,
                (question_id,),
            ).fetchall()
        return [dict(r) for r in rows]
