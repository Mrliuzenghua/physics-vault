from __future__ import annotations

from contextlib import closing

from ..database import connect_db
from ..paths import default_db_path
from ..schemas.embedding_status import EmbeddingStatusItem


class EmbeddingStatusRepository:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def list_question_embeddings(self) -> list[EmbeddingStatusItem]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT model_name, model_version, vector_type, COUNT(*) AS owner_count,
                       MAX(updated_at) AS last_updated_at
                FROM embeddings
                WHERE owner_type = 'question'
                GROUP BY model_name, model_version, vector_type
                ORDER BY owner_count DESC, model_name, vector_type
                """
            ).fetchall()
        return [EmbeddingStatusItem.model_validate(dict(row)) for row in rows]
