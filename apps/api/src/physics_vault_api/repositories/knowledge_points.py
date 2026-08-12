from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from ..database import connect_db
from ..paths import default_db_path
from ..schemas.knowledge_points import KnowledgePointItem, QuestionKnowledgePointBatchItem, QuestionKnowledgePointLink, QuestionKnowledgePointUpsert


class KnowledgePointRepository:
    """Read-only knowledge-point aggregates from the canonical question bank."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path) if db_path else None

    @property
    def database_path(self) -> str | None:
        """Return the explicit database path when one was supplied."""
        return self._db_path

    def question_counts_by_topic3(self) -> dict[str, int]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT topic3_id, COUNT(DISTINCT question_id) AS count
                FROM question_knowledge_points
                GROUP BY topic3_id
                """
            ).fetchall()
        return {str(row["topic3_id"]): int(row["count"]) for row in rows}

    def list(
        self,
        *,
        topic1_id: str | None,
        topic1_name: str | None,
        topic2_id: str | None,
        topic2_name: str | None,
        query: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[KnowledgePointItem]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT
                    topic3_id, topic3_name, topic2_id, topic2_name,
                    topic1_id, topic1_name, source_chapter, status, note
                FROM knowledge_points
                WHERE (? IS NULL OR topic1_id = ?)
                  AND (? IS NULL OR topic1_name = ?)
                  AND (? IS NULL OR topic2_id = ?)
                  AND (? IS NULL OR topic2_name = ?)
                  AND (? IS NULL OR status = ?)
                  AND (
                      ? IS NULL
                      OR topic1_name LIKE '%' || ? || '%'
                      OR topic2_name LIKE '%' || ? || '%'
                      OR topic3_name LIKE '%' || ? || '%'
                      OR topic1_id LIKE '%' || ? || '%'
                      OR topic2_id LIKE '%' || ? || '%'
                      OR topic3_id LIKE '%' || ? || '%'
                  )
                ORDER BY topic1_id, topic2_id, topic3_id
                LIMIT ? OFFSET ?
                """,
                (
                    topic1_id, topic1_id, topic1_name, topic1_name,
                    topic2_id, topic2_id, topic2_name, topic2_name,
                    status, status,
                    query, query, query, query, query, query, query,
                    limit, offset,
                ),
            ).fetchall()
        return [KnowledgePointItem.model_validate(dict(row)) for row in rows]

    def list_for_question(self, question_id: str) -> list[QuestionKnowledgePointLink] | None:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            exists = connection.execute(
                "SELECT 1 FROM questions WHERE question_id = ?", (question_id,)
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """
                SELECT rank, topic1_id, topic1_name, topic2_id, topic2_name,
                       topic3_id, topic3_name, source_chapter, source, confidence, note
                FROM question_knowledge_points_view
                WHERE question_id = ?
                ORDER BY rank
                """,
                (question_id,),
            ).fetchall()
        return [QuestionKnowledgePointLink.model_validate(dict(row)) for row in rows]

    def replace_for_question(
        self, question_id: str, items: list[QuestionKnowledgePointBatchItem]
    ) -> list[QuestionKnowledgePointLink] | None:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path)) as connection:
            if not self._question_exists(connection, question_id):
                return None
            self._ensure_active_topics(connection, [item.topic3_id for item in items])
            try:
                connection.execute("DELETE FROM question_knowledge_points WHERE question_id = ? AND rank BETWEEN 1 AND 3", (question_id,))
                connection.executemany(
                    """INSERT INTO question_knowledge_points
                    (link_id, question_id, rank, topic3_id, source, confidence, note, created_at, updated_at)
                    VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    [(question_id, item.rank, item.topic3_id, item.source, item.confidence, item.note) for item in items],
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError("Knowledge point replacement failed") from exc
        return self.list_for_question(question_id)

    def validate_replacement_for_question(
        self, question_id: str, items: list[QuestionKnowledgePointBatchItem]
    ) -> list[QuestionKnowledgePointLink] | None:
        """Confirm that a planned replacement still targets active knowledge points."""
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            if not self._question_exists(connection, question_id):
                return None
            self._ensure_active_topics(connection, [item.topic3_id for item in items])
        return self.list_for_question(question_id)

    def upsert_for_question(
        self, question_id: str, rank: int, item: QuestionKnowledgePointUpsert
    ) -> QuestionKnowledgePointLink | None:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path)) as connection:
            if not self._question_exists(connection, question_id):
                return None
            self._ensure_active_topics(connection, [item.topic3_id])
            try:
                connection.execute(
                    """INSERT INTO question_knowledge_points
                    (link_id, question_id, rank, topic3_id, source, confidence, note, created_at, updated_at)
                    VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(question_id, rank) DO UPDATE SET topic3_id=excluded.topic3_id,
                    source=excluded.source, confidence=excluded.confidence, note=excluded.note, updated_at=CURRENT_TIMESTAMP""",
                    (question_id, rank, item.topic3_id, item.source, item.confidence, item.note),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError("This question already uses the same topic3_id at another rank") from exc
            row = connection.execute(
                """SELECT rank, topic1_id, topic1_name, topic2_id, topic2_name, topic3_id,
                topic3_name, source_chapter, source, confidence, note
                FROM question_knowledge_points_view WHERE question_id = ? AND rank = ?""",
                (question_id, rank),
            ).fetchone()
        return QuestionKnowledgePointLink.model_validate(dict(row)) if row else None

    def delete_for_question(self, question_id: str, rank: int) -> None:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path)) as connection:
            connection.execute("DELETE FROM question_knowledge_points WHERE question_id = ? AND rank = ?", (question_id, rank))
            connection.commit()

    @staticmethod
    def _question_exists(connection, question_id: str) -> bool:
        return connection.execute("SELECT 1 FROM questions WHERE question_id = ?", (question_id,)).fetchone() is not None

    @staticmethod
    def _ensure_active_topics(connection, topic3_ids: list[str]) -> None:
        placeholders = ",".join("?" for _ in topic3_ids)
        found = {str(row["topic3_id"]) for row in connection.execute(
            f"SELECT topic3_id FROM knowledge_points WHERE topic3_id IN ({placeholders}) AND status = 'active'", topic3_ids
        ).fetchall()}
        missing = sorted(set(topic3_ids) - found)
        if missing:
            raise LookupError(f"Knowledge point not found: {', '.join(missing)}")
