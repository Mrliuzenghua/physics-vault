from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from ..paths import default_db_path, default_review_db_path


SUPPORTED_ROLLBACK_TYPES = {
    "tag_normalization",
    "knowledge_binding_normalization",
    "return_to_review",
}


class ChangeAuditService:
    """Read controlled canonical DB changes and safely preview/apply rollbacks."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        review_db_path: str | Path | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path else default_db_path()
        self._review_db_path = Path(review_db_path) if review_db_path else default_review_db_path()

    def list_batches(
        self,
        *,
        change_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        limit = min(max(int(limit or 50), 1), 200)
        params: list[Any] = []
        where_parts: list[str] = []
        if change_type and str(change_type).strip().lower() not in {"all", "*", "全部"}:
            where_parts.append("change_type = ?")
            params.append(str(change_type).strip())
        if status and str(status).strip().lower() not in {"all", "*", "全部"}:
            where_parts.append("status = ?")
            params.append(str(status).strip())
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        params.append(limit)

        with _connect_standard(self._db_path, writable=True) as conn:
            _ensure_change_audit_schema(conn)
            rows = conn.execute(
                f"""
                SELECT batch_id, change_type, reason, source, status, target_count,
                       changed_count, created_at, applied_at, rolled_back_at, rollback_reason
                FROM change_batches
                {where_sql}
                ORDER BY COALESCE(applied_at, created_at) DESC, batch_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return {
            "ok": True,
            "items": [dict(row) for row in rows],
            "total": len(rows),
            "limit": limit,
            "canonical_database_path": str(self._db_path),
            "review_database_path": str(self._review_db_path),
        }

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        return _load_change_batch(batch_id, self._db_path, self._review_db_path)

    def rollback_batch(
        self,
        batch_id: str,
        *,
        dry_run: bool = True,
        reason: str | None = None,
        allow_conflicts: bool = False,
    ) -> dict[str, Any]:
        if not dry_run and not str(reason or "").strip():
            return {"ok": False, "error": "确认回滚时必须填写原因，便于审计。"}

        batch = _load_change_batch(batch_id, self._db_path, self._review_db_path)
        if not batch.get("ok"):
            return batch

        info = batch["batch"]
        if info["status"] == "rolled_back":
            return {"ok": False, "batch_id": batch_id, "error": "该批次已经回滚。", "batch": info}
        if info["status"] != "applied":
            return {"ok": False, "batch_id": batch_id, "error": f"该批次状态为 {info['status']}，不能回滚。", "batch": info}

        change_type = info["change_type"]
        if change_type not in SUPPORTED_ROLLBACK_TYPES:
            return {"ok": False, "batch_id": batch_id, "error": f"暂不支持回滚类型：{change_type}。"}

        preview_items = _build_rollback_preview(change_type, batch["items"], self._db_path)
        conflicts = [item for item in preview_items if item["status"] == "current_value_conflict"]
        rollbackable = [item for item in preview_items if item["status"] in {"will_rollback", "already_rolled_back"}]
        changed = [item for item in preview_items if item["status"] == "will_rollback"]

        if conflicts and not dry_run and not allow_conflicts:
            return {
                "ok": False,
                "batch_id": batch_id,
                "dry_run": dry_run,
                "error": "当前值与该批次记录的修改后值不一致，可能已有后续修改；请先预览，确认后再允许冲突回滚。",
                "conflict_count": len(conflicts),
                "items": preview_items,
            }

        if not dry_run and changed:
            with _connect_standard(self._db_path, writable=True) as conn:
                if change_type == "tag_normalization":
                    _apply_tag_rollback(conn, changed)
                elif change_type == "knowledge_binding_normalization":
                    _apply_knowledge_binding_rollback(conn, changed, reason)
                elif change_type == "return_to_review":
                    _apply_return_to_review_rollback(conn, changed)
                conn.execute(
                    """
                    UPDATE change_batches
                    SET status = 'rolled_back',
                        rolled_back_at = CURRENT_TIMESTAMP,
                        rollback_reason = ?
                    WHERE batch_id = ?
                    """,
                    (reason, info["batch_id"]),
                )
                conn.commit()
            if change_type == "return_to_review":
                _mark_review_queue_rolled_back(changed, self._review_db_path)

        return {
            "ok": True,
            "batch_id": info["batch_id"],
            "change_type": change_type,
            "dry_run": dry_run,
            "requires_confirmation": dry_run and bool(changed),
            "rollbackable_count": len(rollbackable),
            "changed_count": len(changed),
            "conflict_count": len(conflicts),
            "items": preview_items,
            "batch": info,
        }


def _connect_standard(path: Path, *, writable: bool) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if writable:
        conn = sqlite3.connect(path)
    else:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _connect_review(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_review_db_schema(conn)
    return conn


def _ensure_change_audit_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS change_batches (
            batch_id TEXT PRIMARY KEY,
            change_type TEXT NOT NULL,
            reason TEXT,
            source TEXT NOT NULL DEFAULT 'physics_vault_mcp',
            status TEXT NOT NULL DEFAULT 'applied',
            target_count INTEGER NOT NULL DEFAULT 0,
            changed_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_at TEXT
        )
        """
    )
    for column_sql in [
        "ALTER TABLE change_batches ADD COLUMN rolled_back_at TEXT",
        "ALTER TABLE change_batches ADD COLUMN rollback_reason TEXT",
    ]:
        try:
            conn.execute(column_sql)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS change_items (
            item_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            before_value_json TEXT,
            after_value_json TEXT,
            status TEXT NOT NULL DEFAULT 'changed',
            risk_level TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(batch_id) REFERENCES change_batches(batch_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_change_items_batch
        ON change_items(batch_id, entity_type, entity_id)
        """
    )


def _ensure_review_db_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
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
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_queue_work
        ON review_queue(status, queue_type, priority, updated_at)
        """
    )
    conn.commit()


def _load_change_batch(batch_id: str, db_path: Path, review_db_path: Path) -> dict[str, Any]:
    bid = str(batch_id or "").strip()
    if not bid:
        return {"ok": False, "error": "batch_id 不能为空。"}
    with _connect_standard(db_path, writable=True) as conn:
        _ensure_change_audit_schema(conn)
        batch_row = conn.execute(
            """
            SELECT batch_id, change_type, reason, source, status, target_count,
                   changed_count, created_at, applied_at, rolled_back_at, rollback_reason
            FROM change_batches
            WHERE batch_id = ?
            """,
            (bid,),
        ).fetchone()
        if batch_row is None:
            return {"ok": False, "batch_id": bid, "status": "missing", "error": "变更批次不存在。"}
        item_rows = conn.execute(
            """
            SELECT item_id, batch_id, entity_type, entity_id, field_name,
                   before_value_json, after_value_json, status, risk_level, created_at
            FROM change_items
            WHERE batch_id = ?
            ORDER BY created_at, item_id
            """,
            (bid,),
        ).fetchall()

    items = []
    for row in item_rows:
        item = dict(row)
        item["before_value"] = _parse_json_value(item.pop("before_value_json"))
        item["after_value"] = _parse_json_value(item.pop("after_value_json"))
        items.append(item)
    return {
        "ok": True,
        "batch": dict(batch_row),
        "items": items,
        "canonical_database_path": str(db_path),
        "review_database_path": str(review_db_path),
    }


def _build_rollback_preview(
    change_type: str,
    items: list[dict[str, Any]],
    db_path: Path,
) -> list[dict[str, Any]]:
    if change_type == "tag_normalization":
        return _build_tag_rollback_preview(items, db_path)
    if change_type == "knowledge_binding_normalization":
        return _build_knowledge_binding_rollback_preview(items, db_path)
    if change_type == "return_to_review":
        return _build_return_to_review_rollback_preview(items, db_path)
    return []


def _build_tag_rollback_preview(items: list[dict[str, Any]], db_path: Path) -> list[dict[str, Any]]:
    question_ids = [str(item["entity_id"]) for item in items]
    placeholders = ",".join("?" for _ in question_ids) or "?"
    params = question_ids or [""]
    with _connect_standard(db_path, writable=False) as conn:
        rows = conn.execute(
            f"""
            SELECT question_id, tags_json
            FROM question_text_index
            WHERE question_id IN ({placeholders})
            """,
            params,
        ).fetchall()
    current = {row["question_id"]: _parse_tags(row["tags_json"]) for row in rows}
    preview = []
    for item in items:
        qid = str(item["entity_id"])
        before = _normalize_tags(item.get("before_value"))
        after = _normalize_tags(item.get("after_value"))
        now = current.get(qid, [])
        preview.append(_preview_item(qid, item["field_name"], now, before, after))
    return preview


def _build_knowledge_binding_rollback_preview(
    items: list[dict[str, Any]],
    db_path: Path,
) -> list[dict[str, Any]]:
    question_ids = [str(item["entity_id"]) for item in items]
    placeholders = ",".join("?" for _ in question_ids) or "?"
    params = question_ids or [""]
    current: dict[str, list[str]] = {qid: [] for qid in question_ids}
    with _connect_standard(db_path, writable=False) as conn:
        rows = conn.execute(
            f"""
            SELECT question_id, topic3_id
            FROM question_knowledge_points
            WHERE question_id IN ({placeholders})
            ORDER BY question_id, rank, topic3_id
            """,
            params,
        ).fetchall()
    for row in rows:
        current.setdefault(row["question_id"], []).append(row["topic3_id"])
    preview = []
    for item in items:
        qid = str(item["entity_id"])
        before = [str(value) for value in (item.get("before_value") or [])]
        after = [str(value) for value in (item.get("after_value") or [])]
        now = current.get(qid, [])
        preview.append(_preview_item(qid, item["field_name"], now, before, after))
    return preview


def _build_return_to_review_rollback_preview(
    items: list[dict[str, Any]],
    db_path: Path,
) -> list[dict[str, Any]]:
    question_ids = [str(item["entity_id"]) for item in items]
    placeholders = ",".join("?" for _ in question_ids) or "?"
    params = question_ids or [""]
    with _connect_standard(db_path, writable=False) as conn:
        rows = conn.execute(
            f"""
            SELECT question_id, status, review_status
            FROM questions
            WHERE question_id IN ({placeholders})
            """,
            params,
        ).fetchall()
    current = {row["question_id"]: {"status": row["status"], "review_status": row["review_status"]} for row in rows}
    preview = []
    for item in items:
        qid = str(item["entity_id"])
        before = item.get("before_value") if isinstance(item.get("before_value"), dict) else {}
        after = item.get("after_value") if isinstance(item.get("after_value"), dict) else {}
        now = current.get(qid, {})
        preview.append(_preview_item(qid, item["field_name"], now, before, after))
    return preview


def _preview_item(
    question_id: str,
    field_name: str,
    current_value: Any,
    rollback_to: Any,
    expected_current: Any,
) -> dict[str, Any]:
    if current_value == rollback_to:
        status = "already_rolled_back"
    elif current_value == expected_current:
        status = "will_rollback"
    else:
        status = "current_value_conflict"
    return {
        "question_id": question_id,
        "field_name": field_name,
        "current_value": current_value,
        "rollback_to": rollback_to,
        "expected_current": expected_current,
        "status": status,
    }


def _apply_tag_rollback(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    for item in items:
        conn.execute(
            """
            INSERT INTO question_text_index (question_id, tags_json, source_text, created_at, updated_at)
            VALUES (?, ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(question_id) DO UPDATE SET
                tags_json = excluded.tags_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (item["question_id"], json.dumps(item["rollback_to"], ensure_ascii=False)),
        )


def _apply_knowledge_binding_rollback(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
    reason: str | None,
) -> None:
    topic_ids = sorted({topic_id for item in items for topic_id in item.get("rollback_to", [])})
    topics = _fetch_topics(conn, topic_ids)
    for item in items:
        qid = item["question_id"]
        rollback_to = [str(topic_id) for topic_id in item.get("rollback_to", [])]
        conn.execute("DELETE FROM question_knowledge_points WHERE question_id = ?", (qid,))
        for rank, topic3_id in enumerate(rollback_to, start=1):
            conn.execute(
                """
                INSERT INTO question_knowledge_points (
                    link_id, question_id, topic3_id, rank, source, confidence, note,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'rollback', 1.0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (f"QKP-{qid}-{rank}-{_short_id()}", qid, topic3_id, rank, reason),
            )
        primary = _topic_payload(topics[rollback_to[0]]) if rollback_to and rollback_to[0] in topics else {}
        conn.execute(
            """
            UPDATE questions
            SET module = ?, topic2 = ?, topic3 = ?, updated_at = CURRENT_TIMESTAMP
            WHERE question_id = ?
            """,
            (
                primary.get("topic3_name"),
                primary.get("topic2_name"),
                primary.get("topic3_name"),
                qid,
            ),
        )


def _apply_return_to_review_rollback(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    for item in items:
        rollback_to = item.get("rollback_to") if isinstance(item.get("rollback_to"), dict) else {}
        conn.execute(
            """
            UPDATE questions
            SET status = ?,
                review_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE question_id = ?
            """,
            (
                rollback_to.get("status"),
                rollback_to.get("review_status"),
                item["question_id"],
            ),
        )


def _mark_review_queue_rolled_back(items: list[dict[str, Any]], review_db_path: Path) -> None:
    with _connect_review(review_db_path) as conn:
        for item in items:
            conn.execute(
                """
                UPDATE review_queue
                SET status = 'rolled_back',
                    updated_at = CURRENT_TIMESTAMP
                WHERE entity_type = 'question'
                  AND entity_id = ?
                  AND queue_type = 'rework'
                  AND status = 'pending'
                """,
                (item["question_id"],),
            )
        conn.commit()


def _fetch_topics(conn: sqlite3.Connection, topic3_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not topic3_ids:
        return {}
    placeholders = ",".join("?" for _ in topic3_ids)
    rows = conn.execute(
        f"""
        SELECT topic1_id, topic1_name, topic2_id, topic2_name, topic3_id, topic3_name, source_chapter, status
        FROM knowledge_points
        WHERE topic3_id IN ({placeholders}) AND status = 'active'
        """,
        topic3_ids,
    ).fetchall()
    return {row["topic3_id"]: row for row in rows}


def _topic_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "topic1_id": row["topic1_id"],
        "topic1_name": row["topic1_name"],
        "topic2_id": row["topic2_id"],
        "topic2_name": row["topic2_name"],
        "topic3_id": row["topic3_id"],
        "topic3_name": row["topic3_name"],
        "source_chapter": row["source_chapter"],
    }


def _parse_json_value(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list, int, float, bool)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return raw


def _parse_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return _normalize_tags(raw)
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
        return _normalize_tags(parsed)
    except (TypeError, json.JSONDecodeError):
        return _normalize_tags(str(raw).replace("，", ",").replace("、", ",").split(","))


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace("，", ",").replace("、", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        tag = str(item).strip()
        if not tag:
            continue
        tag = " ".join(tag.split())
        if len(tag) > 30:
            tag = tag[:30].strip()
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def _short_id() -> str:
    return uuid.uuid4().hex[:12]
