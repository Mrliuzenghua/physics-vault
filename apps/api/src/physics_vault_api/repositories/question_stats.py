from __future__ import annotations

from contextlib import closing

from ..database import connect_db
from ..paths import default_db_path


class QuestionStatsRepository:
    """Read-only aggregate queries over the canonical question bank."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def status_counts(self) -> dict[str, int]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM questions GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
