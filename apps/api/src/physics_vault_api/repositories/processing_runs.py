from __future__ import annotations

from contextlib import closing
from typing import Any

from ..database import connect_db
from ..paths import default_db_path


class ProcessingRunRepository:
    """Read-only access to historical processing pipeline records."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def list(
        self,
        *,
        pipeline_name: str | None,
        paper_id: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    pipeline_name,
                    pipeline_version,
                    paper_id,
                    question_id,
                    status,
                    started_at,
                    finished_at,
                    operator,
                    summary_json
                FROM processing_runs
                WHERE (? IS NULL OR pipeline_name = ?)
                  AND (? IS NULL OR paper_id = ?)
                  AND (? IS NULL OR status = ?)
                ORDER BY started_at DESC, run_id DESC
                LIMIT ? OFFSET ?
                """,
                (pipeline_name, pipeline_name, paper_id, paper_id, status, status, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]
