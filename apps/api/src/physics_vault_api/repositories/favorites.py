"""Repository for favorite groups and star ratings (SQLite)."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path

logger = logging.getLogger(__name__)

CREATE_GROUPS = """
CREATE TABLE IF NOT EXISTS favorite_groups (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

CREATE_ITEMS = """
CREATE TABLE IF NOT EXISTS favorite_items (
    question_id TEXT NOT NULL,
    group_id    TEXT,
    star_rating INTEGER NOT NULL DEFAULT 0 CHECK(star_rating >= 0 AND star_rating <= 5),
    added_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (question_id),
    FOREIGN KEY (group_id) REFERENCES favorite_groups(id) ON DELETE SET NULL
)
"""


def _resolve_db_path(path: str | None = None) -> Path:
    return Path(path) if path else default_db_path()


class FavoritesRepository:
    """Data access for favorite groups and star ratings."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._ensure_tables()

    def _db_available(self) -> bool:
        return self._db_path.exists()

    def _get_connection(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    def _ensure_tables(self) -> None:
        if not self._db_available():
            return
        try:
            with closing(self._get_connection()) as conn:
                conn.execute(CREATE_GROUPS)
                conn.execute(CREATE_ITEMS)
                conn.commit()
        except Exception:
            logger.exception("Failed to create favorite tables")

    # ── Groups CRUD ───────────────────────────────────────────────

    def list_groups(self) -> list[dict[str, Any]]:
        if not self._db_available():
            return []
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT g.*, COALESCE(fi.cnt, 0) AS question_count
                FROM favorite_groups g
                LEFT JOIN (
                    SELECT group_id, COUNT(*) AS cnt
                    FROM favorite_items WHERE group_id IS NOT NULL
                    GROUP BY group_id
                ) fi ON fi.group_id = g.id
                ORDER BY g.sort_order, g.name
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def create_group(self, name: str) -> dict[str, Any]:
        gid = f"FAV-{uuid.uuid4().hex[:12]}"
        with closing(self._get_connection()) as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM favorite_groups"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO favorite_groups (id, name, sort_order) VALUES (?, ?, ?)",
                (gid, name, max_order),
            )
            conn.commit()
        return {"id": gid, "name": name, "question_count": 0, "sort_order": max_order}

    def update_group(self, group_id: str, name: str) -> bool:
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                "UPDATE favorite_groups SET name = ?, updated_at = datetime('now') WHERE id = ?",
                (name, group_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_group(self, group_id: str) -> bool:
        with closing(self._get_connection()) as conn:
            # Set items in this group to NULL (ungrouped), don't delete them
            conn.execute(
                "UPDATE favorite_items SET group_id = NULL WHERE group_id = ?",
                (group_id,),
            )
            cur = conn.execute("DELETE FROM favorite_groups WHERE id = ?", (group_id,))
            conn.commit()
            return cur.rowcount > 0

    # ── Items (star + group assignment) ───────────────────────────

    def add_or_update(self, question_id: str, group_id: str | None, star_rating: int | None) -> bool:
        """Insert or update a favorite item. Returns True if inserted, False if updated."""
        with closing(self._get_connection()) as conn:
            existing = conn.execute(
                "SELECT question_id FROM favorite_items WHERE question_id = ?",
                (question_id,),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO favorite_items (question_id, group_id, star_rating)
                    VALUES (?, ?, ?)
                    """,
                    (question_id, group_id, star_rating or 0),
                )
                conn.commit()
                return True
            else:
                parts = []
                params: list[Any] = []
                if group_id is not None:
                    parts.append("group_id = ?")
                    params.append(group_id)
                if star_rating is not None:
                    parts.append("star_rating = ?")
                    params.append(star_rating)
                if parts:
                    params.append(question_id)
                    conn.execute(
                        f"UPDATE favorite_items SET {', '.join(parts)} WHERE question_id = ?",
                        params,
                    )
                conn.commit()
                return False

    def batch_assign(self, question_ids: list[str], group_id: str | None, star_rating: int | None) -> dict[str, Any]:
        """Batch assign group and/or star to multiple questions."""
        success = 0
        skipped = 0
        failed = 0
        with closing(self._get_connection()) as conn:
            for qid in question_ids:
                try:
                    existing = conn.execute(
                        "SELECT question_id FROM favorite_items WHERE question_id = ?",
                        (qid,),
                    ).fetchone()

                    if existing is None:
                        conn.execute(
                            "INSERT INTO favorite_items (question_id, group_id, star_rating) VALUES (?, ?, ?)",
                            (qid, group_id, star_rating or 0),
                        )
                    else:
                        parts = []
                        params: list[Any] = []
                        if group_id is not None:
                            parts.append("group_id = ?")
                            params.append(group_id)
                        if star_rating is not None:
                            parts.append("star_rating = ?")
                            params.append(star_rating)
                        if parts:
                            params.append(qid)
                            conn.execute(
                                f"UPDATE favorite_items SET {', '.join(parts)} WHERE question_id = ?",
                                params,
                            )
                        else:
                            skipped += 1
                            continue
                    success += 1
                except Exception:
                    failed += 1
            conn.commit()
        return {"total": len(question_ids), "success_count": success, "skipped_count": skipped, "failed_count": failed}

    def remove(self, question_ids: list[str]) -> int:
        """Remove questions from favorites entirely. Returns count removed."""
        if not question_ids:
            return 0
        placeholders = ",".join("?" for _ in question_ids)
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                f"DELETE FROM favorite_items WHERE question_id IN ({placeholders})",
                question_ids,
            )
            conn.commit()
            return cur.rowcount

    def get_item(self, question_id: str) -> dict[str, Any] | None:
        if not self._db_available():
            return None
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                """
                SELECT fi.*, fg.name AS group_name
                FROM favorite_items fi
                LEFT JOIN favorite_groups fg ON fg.id = fi.group_id
                WHERE fi.question_id = ?
                """,
                (question_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_favorites(
        self,
        group_id: str | None = None,
        min_star: int = 0,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return favorite items with group info, filtered and sorted."""
        if not self._db_available():
            return [], 0

        where = ["1=1"]
        params: list[Any] = []

        if group_id is not None:
            where.append("fi.group_id = ?")
            params.append(group_id)
        elif group_id == "__ungrouped__":
            where.append("fi.group_id IS NULL")

        if min_star > 0:
            where.append("fi.star_rating >= ?")
            params.append(min_star)

        where_clause = " AND ".join(where)

        with closing(self._get_connection()) as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM favorite_items fi WHERE {where_clause}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"""
                SELECT fi.*, fg.name AS group_name
                FROM favorite_items fi
                LEFT JOIN favorite_groups fg ON fg.id = fi.group_id
                WHERE {where_clause}
                ORDER BY fi.star_rating DESC, fi.added_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

        return [dict(r) for r in rows], total

    def get_favorite_ids(self) -> set[str]:
        """Return all question_ids that are favorited."""
        if not self._db_available():
            return set()
        with closing(self._get_connection()) as conn:
            rows = conn.execute("SELECT question_id FROM favorite_items").fetchall()
        return {r["question_id"] for r in rows}
