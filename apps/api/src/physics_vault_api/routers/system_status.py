from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter

from ..schemas.contracts import HealthResponse, ObjectMapResponse
from ..database import connect_db
from ..paths import default_db_path
from ..repositories.question_search import QuestionSearchRepository


def build_system_status_router(search_repo: QuestionSearchRepository) -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system-status"])

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Return the canonical API health response used by web domain clients."""
        return HealthResponse(status="ok")

    @router.get("/db-status", response_model=ObjectMapResponse)
    def db_status() -> dict[str, Any]:
        db_path = default_db_path()
        status: dict[str, Any] = {
            "db_path": str(db_path),
            "db_exists": db_path.exists(),
            "search_uses_mock": bool(getattr(search_repo, "_mock", False)),
            "questions_count": 0,
            "browsable_questions_count": 0,
            "text_index_count": 0,
            "fts_count": 0,
            "error": None,
        }
        if not db_path.exists():
            return status

        try:
            with connect_db(db_path, writable=False) as conn:
                status["questions_count"] = _count_table(conn, "questions")
                status["browsable_questions_count"] = _count_browsable_questions(conn)
                status["text_index_count"] = _count_table(conn, "question_text_index")
                status["fts_count"] = _count_table(conn, "question_search_fts")
        except Exception as exc:  # noqa: BLE001
            status["error"] = str(exc)
        return status

    return router


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _count_browsable_questions(conn: sqlite3.Connection) -> int:
    """Match the default question-search scope used by the teaching UI."""
    row = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE COALESCE(status, '') != 'archived_duplicate'"
    ).fetchone()
    return int(row[0])
