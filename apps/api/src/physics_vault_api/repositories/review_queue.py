from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..paths import default_db_path, default_review_db_path


class ReviewQueueRepository:
    """Review queue storage.

    The live question bank remains in the canonical database, while review
    queue rows live in the review workspace database.  Older local databases
    may still contain review_queue rows in the canonical DB. Recovery from such
    data is an explicit maintenance action, never a normal application startup
    behavior.
    """

    def __init__(
        self,
        db_path: str | None = None,
        *,
        legacy_db_path: str | None = None,
        migrate_legacy: bool = False,
        delete_legacy_after_migrate: bool = False,
    ) -> None:
        self._db_path = Path(db_path) if db_path else default_review_db_path()
        self._legacy_db_path = Path(legacy_db_path) if legacy_db_path else default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        if migrate_legacy:
            self.migrate_legacy(delete_legacy_after_migrate=delete_legacy_after_migrate)
        self.delete_orphan_question_rows()

    def list(
        self,
        *,
        status: str | None = None,
        queue_type: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        limit = min(max(int(limit or 80), 1), 500)
        where_parts: list[str] = []
        params: list[Any] = []
        if status and status.lower() not in {"all", "*", "全部"}:
            where_parts.append("status = ?")
            params.append(status)
        if queue_type and queue_type.lower() not in {"all", "*", "全部"}:
            where_parts.append("queue_type = ?")
            params.append(queue_type)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT review_id, entity_type, entity_id, queue_type, status,
                       priority, reason, payload_json, created_at, updated_at
                FROM review_queue
                {where_sql}
                ORDER BY priority DESC, updated_at DESC, created_at DESC, review_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_rework(
        self,
        *,
        review_id: str,
        question_id: str,
        reason: str,
        reviewer: str | None = None,
        priority: int = 5,
    ) -> None:
        payload_json = json.dumps(
            {
                "source": "question_bank_return",
                "reviewer": reviewer,
                "action": "return_to_review",
            },
            ensure_ascii=False,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO review_queue (
                    review_id, entity_type, entity_id, queue_type, status,
                    priority, reason, payload_json, created_at, updated_at
                ) VALUES (?, 'question', ?, 'rework', 'pending', ?, ?, ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (review_id, question_id, priority, reason, payload_json),
            )
            conn.commit()

    def migrate_legacy(self, *, delete_legacy_after_migrate: bool = False) -> int:
        legacy_path = self._legacy_db_path
        if not legacy_path.exists() or legacy_path.resolve() == self._db_path.resolve():
            return 0

        with sqlite3.connect(legacy_path) as source:
            source.row_factory = sqlite3.Row
            if not _table_exists(source, "review_queue"):
                return 0
            rows = source.execute(
                """
                SELECT review_id, entity_type, entity_id, queue_type, status,
                       priority, reason, payload_json, created_at, updated_at
                FROM review_queue
                """
            ).fetchall()

        if not rows:
            return 0

        with self._connect() as target:
            target.executemany(
                """
                INSERT OR IGNORE INTO review_queue (
                    review_id, entity_type, entity_id, queue_type, status,
                    priority, reason, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["review_id"],
                        row["entity_type"],
                        row["entity_id"],
                        row["queue_type"],
                        row["status"],
                        row["priority"],
                        row["reason"],
                        row["payload_json"],
                        row["created_at"],
                        row["updated_at"],
                    )
                    for row in rows
                ],
            )
            target.commit()

        if delete_legacy_after_migrate:
            with sqlite3.connect(legacy_path) as legacy:
                legacy.execute("DELETE FROM review_queue")
                legacy.commit()

        return len(rows)

    def delete_orphan_question_rows(self) -> int:
        """Remove queue rows that reference questions no longer in the canonical DB."""

        if not self._legacy_db_path.exists():
            return 0
        with self._connect() as review_conn:
            rows = review_conn.execute(
                """
                SELECT review_id, entity_id
                FROM review_queue
                WHERE entity_type = 'question'
                """
            ).fetchall()
            if not rows:
                return 0

            question_ids = [str(row["entity_id"]) for row in rows]
            existing: set[str] = set()
            with sqlite3.connect(self._legacy_db_path) as canonical_conn:
                canonical_conn.row_factory = sqlite3.Row
                if not _table_exists(canonical_conn, "questions"):
                    return 0
                for offset in range(0, len(question_ids), 500):
                    chunk = question_ids[offset : offset + 500]
                    placeholders = ",".join("?" for _ in chunk)
                    found = canonical_conn.execute(
                        f"SELECT question_id FROM questions WHERE question_id IN ({placeholders})",
                        chunk,
                    ).fetchall()
                    existing.update(str(row["question_id"]) for row in found)

            orphan_review_ids = [
                str(row["review_id"])
                for row in rows
                if str(row["entity_id"]) not in existing
            ]
            if not orphan_review_ids:
                return 0

            for offset in range(0, len(orphan_review_ids), 500):
                chunk = orphan_review_ids[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                review_conn.execute(
                    f"DELETE FROM review_queue WHERE review_id IN ({placeholders})",
                    chunk,
                )
            review_conn.commit()
            return len(orphan_review_ids)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection | None = None) -> None:
        close_after = conn is None
        active = conn or sqlite3.connect(self._db_path)
        try:
            active.execute(
                """
                CREATE TABLE IF NOT EXISTS review_queue (
                    review_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL DEFAULT 'question',
                    entity_id TEXT NOT NULL,
                    queue_type TEXT NOT NULL DEFAULT 'manual',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            active.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_review_queue_work
                ON review_queue(status, queue_type, priority, updated_at)
                """
            )
            active.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_review_queue_entity
                ON review_queue(entity_type, entity_id)
                """
            )
            active.commit()
        finally:
            if close_after:
                active.close()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None
