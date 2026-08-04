from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from ..database import connect_db
from ..paths import default_db_path


class PaperDraftConflictError(ValueError):
    """The stored draft changed after the caller last read it."""


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class PaperDraftRepository:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(default_db_path())

    def _get_connection(self) -> sqlite3.Connection:
        return connect_db(self._db_path)

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT draft_id, title, subtitle, source, status, question_count,
                       item_count, total_score, created_at, updated_at
                FROM paper_drafts
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_summary_from_row(row) for row in rows]

    def get(self, draft_id: str) -> dict[str, Any] | None:
        with closing(self._get_connection()) as conn:
            draft = conn.execute(
                """
                SELECT *
                FROM paper_drafts
                WHERE draft_id = ?
                """,
                (draft_id,),
            ).fetchone()
            if draft is None:
                return None

            items = conn.execute(
                """
                SELECT *
                FROM paper_draft_items
                WHERE draft_id = ?
                ORDER BY position, item_id
                """,
                (draft_id,),
            ).fetchall()

        payload = _summary_from_row(draft)
        payload["items"] = [_item_from_row(row) for row in items]
        payload["metadata"] = _json_loads(draft["metadata_json"], {})
        payload["quality_report"] = _json_loads(draft["quality_report_json"], {})
        return payload

    def get_latest(self) -> dict[str, Any] | None:
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                """
                SELECT draft_id
                FROM paper_drafts
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self.get(row["draft_id"])

    def upsert(
        self,
        *,
        draft_id: str | None,
        base_updated_at: str | None,
        title: str,
        subtitle: str | None,
        source: str,
        status: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any],
        quality_report: dict[str, Any],
        question_count: int,
        item_count: int,
        total_score: float,
    ) -> dict[str, Any]:
        resolved_id = draft_id or _make_id("draft")
        revision_time = f"{datetime.now(timezone.utc).isoformat(timespec='microseconds')}-{uuid.uuid4().hex[:6]}"
        with closing(self._get_connection()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT updated_at FROM paper_drafts WHERE draft_id = ?",
                (resolved_id,),
            ).fetchone()
            if (
                current is not None
                and base_updated_at is not None
                and str(current["updated_at"] or "") != str(base_updated_at)
            ):
                conn.rollback()
                raise PaperDraftConflictError(
                    "组卷草稿已被其他操作更新，请刷新后重试。"
                )
            conn.execute(
                """
                INSERT INTO paper_drafts (
                    draft_id, title, subtitle, source, status, question_count,
                    item_count, total_score, metadata_json, quality_report_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_id) DO UPDATE SET
                    title = excluded.title,
                    subtitle = excluded.subtitle,
                    source = excluded.source,
                    status = excluded.status,
                    question_count = excluded.question_count,
                    item_count = excluded.item_count,
                    total_score = excluded.total_score,
                    metadata_json = excluded.metadata_json,
                    quality_report_json = excluded.quality_report_json,
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_id,
                    title,
                    subtitle,
                    source,
                    status,
                    question_count,
                    item_count,
                    total_score,
                    _json_dumps(metadata),
                    _json_dumps(quality_report),
                    revision_time,
                    revision_time,
                ),
            )
            conn.execute("DELETE FROM paper_draft_items WHERE draft_id = ?", (resolved_id,))
            for item in items:
                conn.execute(
                    """
                    INSERT INTO paper_draft_items (
                        item_id, draft_id, position, item_type, question_id,
                        title, section_title, score, payload_json,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                            strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    """,
                    (
                        item["id"],
                        resolved_id,
                        item["position"],
                        item["type"],
                        item.get("question_id"),
                        item.get("title"),
                        item.get("section_title"),
                        item.get("score"),
                        _json_dumps(item.get("payload")),
                    ),
                )
            conn.commit()

        saved = self.get(resolved_id)
        if saved is None:
            raise RuntimeError("paper draft was not saved")
        return saved

    def delete(self, draft_id: str) -> bool:
        with closing(self._get_connection()) as conn:
            cur = conn.execute("DELETE FROM paper_drafts WHERE draft_id = ?", (draft_id,))
            conn.commit()
            return cur.rowcount > 0


def _summary_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["draft_id"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "source": row["source"],
        "status": row["status"],
        "question_count": row["question_count"],
        "item_count": row["item_count"],
        "total_score": row["total_score"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _item_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["item_id"],
        "type": row["item_type"],
        "position": row["position"],
        "question_id": row["question_id"],
        "title": row["title"],
        "section_title": row["section_title"],
        "score": row["score"],
        "payload": _json_loads(row["payload_json"], {}),
    }
