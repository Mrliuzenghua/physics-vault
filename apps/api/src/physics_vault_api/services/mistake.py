"""Mistake marking service 鈥?manages mistake state on questions."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path

from ..schemas.mistake import (
    BatchMarkMistakeResponse,
    MistakeItemResult,
    MistakeStatsResponse,
)

logger = logging.getLogger(__name__)

class MistakeService:
    """Manages mistake marking on questions in the SQLite database."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else default_db_path()
        self._columns_ensured = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark(self, question_id: str, is_mistake: bool) -> dict[str, Any]:
        """Mark or unmark a single question."""
        self._ensure_columns()
        with closing(self._connect()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM questions WHERE question_id = ?", (question_id,)
            ).fetchone()
            if not exists:
                return {"question_id": question_id, "status": "skipped", "message": "棰樼洰涓嶅瓨鍦?}

            if is_mistake:
                conn.execute(
                    "UPDATE questions SET is_mistake = 1, mistake_marked_at = ? WHERE question_id = ?",
                    (_utc_now(), question_id),
                )
                conn.commit()
                return {"question_id": question_id, "status": "marked", "message": "宸插姞鍏ラ敊棰橀泦"}
            else:
                conn.execute(
                    "UPDATE questions SET is_mistake = 0, mistake_marked_at = NULL WHERE question_id = ?",
                    (question_id,),
                )
                conn.commit()
                return {"question_id": question_id, "status": "unmarked", "message": "宸茬Щ鍑洪敊棰橀泦"}

    def batch_mark(self, question_ids: list[str], is_mistake: bool) -> BatchMarkMistakeResponse:
        """Batch mark or unmark questions."""
        self._ensure_columns()
        items: list[MistakeItemResult] = []
        success = 0
        skipped = 0
        failed = 0

        with closing(self._connect()) as conn:
            for qid in question_ids:
                try:
                    exists = conn.execute(
                        "SELECT 1 FROM questions WHERE question_id = ?", (qid,)
                    ).fetchone()
                    if not exists:
                        items.append(MistakeItemResult(question_id=qid, status="skipped", message="棰樼洰涓嶅瓨鍦?))
                        skipped += 1
                        continue

                    if is_mistake:
                        conn.execute(
                            "UPDATE questions SET is_mistake = 1, mistake_marked_at = ? WHERE question_id = ?",
                            (_utc_now(), qid),
                        )
                        items.append(MistakeItemResult(question_id=qid, status="marked", message="宸插姞鍏ラ敊棰橀泦"))
                    else:
                        conn.execute(
                            "UPDATE questions SET is_mistake = 0, mistake_marked_at = NULL WHERE question_id = ?",
                            (qid,),
                        )
                        items.append(MistakeItemResult(question_id=qid, status="unmarked", message="宸茬Щ鍑洪敊棰橀泦"))
                    success += 1
                except Exception as exc:
                    logger.exception("Failed to mark question %s", qid)
                    items.append(MistakeItemResult(question_id=qid, status="failed", message=str(exc)))
                    failed += 1

            conn.commit()

        return BatchMarkMistakeResponse(
            total=len(question_ids),
            success=success,
            skipped=skipped,
            failed=failed,
            items=items,
        )

    def get_stats(self) -> MistakeStatsResponse:
        """Return mistake statistics."""
        self._ensure_columns()
        with closing(self._connect()) as conn:
            total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            mistake_count = conn.execute(
                "SELECT COUNT(*) FROM questions WHERE is_mistake = 1"
            ).fetchone()[0]

            # Recent 7 days
            recent = 0
            try:
                recent = conn.execute(
                    "SELECT COUNT(*) FROM questions WHERE is_mistake = 1 AND mistake_marked_at >= ?",
                    (_recent_7d(),),
                ).fetchone()[0]
            except Exception:
                pass

        return MistakeStatsResponse(
            total_questions=total,
            mistake_count=mistake_count,
            recent_7d_count=recent,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    def _ensure_columns(self) -> None:
        """Add is_mistake / mistake_marked_at columns if they don't exist."""
        if self._columns_ensured:
            return
        try:
            with closing(self._connect()) as conn:
                conn.execute("ALTER TABLE questions ADD COLUMN is_mistake INTEGER DEFAULT 0")
            logger.info("Added column questions.is_mistake")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            with closing(self._connect()) as conn:
                conn.execute("ALTER TABLE questions ADD COLUMN mistake_marked_at TEXT")
            logger.info("Added column questions.mistake_marked_at")
        except sqlite3.OperationalError:
            pass  # Column already exists

        self._columns_ensured = True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recent_7d() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
