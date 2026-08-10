from __future__ import annotations

from contextlib import closing

from ..database import connect_db
from ..paths import default_db_path


class QuestionReviewRepository:
    """Canonical question state needed by the cross-database review workflow."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(default_db_path())

    def get_status(self, question_id: str) -> str | None:
        with closing(connect_db(self._db_path, writable=False)) as connection:
            row = connection.execute(
                "SELECT status FROM questions WHERE question_id = ?", (question_id,)
            ).fetchone()
        return str(row["status"]) if row is not None else None

    def set_status(self, question_id: str, status: str) -> bool:
        with closing(connect_db(self._db_path)) as connection:
            result = connection.execute(
                "UPDATE questions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (status, question_id),
            )
            connection.commit()
        return result.rowcount > 0

    def get_context(self, question_id: str) -> dict | None:
        with closing(connect_db(self._db_path, writable=False)) as connection:
            row = connection.execute(
                """
                SELECT q.question_id, q.module, q.topic2, q.topic3, q.status,
                       q.primary_paper_id, q.primary_question_no, q.vault_markdown_path,
                       qti.stem_text
                FROM questions q
                LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
                WHERE q.question_id = ?
                """,
                (question_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_rejected(self, *, status: str, limit: int, offset: int) -> list[dict]:
        with closing(connect_db(self._db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT question_id, module, topic2, topic3, status, primary_paper_id,
                       primary_question_no, vault_markdown_path
                FROM questions
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_stem_and_status(self, question_id: str, *, stem_text: str, status: str) -> bool:
        with closing(connect_db(self._db_path)) as connection:
            exists = connection.execute(
                "SELECT 1 FROM questions WHERE question_id = ?", (question_id,)
            ).fetchone()
            if exists is None:
                return False
            connection.execute(
                "UPDATE question_text_index SET stem_text = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (stem_text, question_id),
            )
            connection.execute(
                "UPDATE questions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (status, question_id),
            )
            connection.commit()
        return True
