"""Teacher feedback loop for method retrieval and metadata maintenance."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from ..database import connect_db
from ..paths import default_db_path
from .metadata_management import MetadataManagementService
from .method_feature_index import (
    ensure_method_feature_schema,
    refresh_question_method_features,
)


FeedbackVerdict = Literal["correct", "incorrect", "missed"]

_METHOD_KNOWLEDGE = {
    "gravity": (
        "KP-EM-MAGNETIC-COMBINED",
        "KP-EM-MAGNETIC-LORENTZ",
        "KP-MECH-ENERGY-KINETIC",
    ),
    "electric": (
        "KP-EM-MAGNETIC-COMBINED",
        "KP-EM-MAGNETIC-LORENTZ",
        "KP-EM-EFIELD-STRENGTH",
    ),
}


def record_method_retrieval_feedback(
    *,
    question_id: str,
    method_id: str,
    branch: Literal["gravity", "electric"],
    verdict: FeedbackVerdict,
    reason: str | None = None,
    operator: str = "teacher",
    maintain_metadata: bool = True,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(db_path) if db_path else default_db_path()
    clean_question_id = str(question_id or "").strip()
    if not clean_question_id:
        raise ValueError("question_id 不能为空。")
    if verdict not in {"correct", "incorrect", "missed"}:
        raise ValueError("verdict 必须是 correct、incorrect 或 missed。")
    clean_reason = " ".join(str(reason or "").split())[:500] or None
    clean_operator = " ".join(str(operator or "teacher").split())[:100] or "teacher"
    feedback_id = f"MRF-{uuid.uuid4().hex[:16]}"

    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        question = conn.execute(
            "SELECT question_id FROM questions WHERE question_id = ?",
            (clean_question_id,),
        ).fetchone()
        if question is None:
            raise ValueError(f"正式题库中不存在题目：{clean_question_id}")
        text_row = conn.execute(
            "SELECT tags_json FROM question_text_index WHERE question_id = ?",
            (clean_question_id,),
        ).fetchone()
        try:
            tags = json.loads(str(text_row["tags_json"] or "[]")) if text_row else []
        except (TypeError, ValueError, json.JSONDecodeError):
            tags = []
        existing_topic_ids = [
            str(row["topic3_id"])
            for row in conn.execute(
                """
                SELECT topic3_id FROM question_knowledge_points
                WHERE question_id = ? ORDER BY rank, topic3_id
                """,
                (clean_question_id,),
            ).fetchall()
        ]
        conn.execute(
            """
            INSERT INTO method_retrieval_feedback (
                feedback_id, question_id, method_id, branch, verdict,
                reason, operator, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """,
            (
                feedback_id,
                clean_question_id,
                method_id,
                branch,
                verdict,
                clean_reason,
                clean_operator,
            ),
        )
        available_topic_ids = {
            str(row["topic3_id"])
            for row in conn.execute(
                f"""
                SELECT topic3_id FROM knowledge_points
                WHERE topic3_id IN ({','.join('?' for _ in _METHOD_KNOWLEDGE[branch])})
                  AND status = 'active'
                """,
                _METHOD_KNOWLEDGE[branch],
            ).fetchall()
        }
        conn.commit()
    finally:
        conn.close()

    metadata_result: dict[str, Any] | None = None
    if maintain_metadata:
        branch_tag = "重力配速法" if branch == "gravity" else "电场配速法"
        clean_tags = list(dict.fromkeys(str(tag).strip() for tag in tags if str(tag).strip()))
        if verdict in {"correct", "missed"}:
            clean_tags = list(dict.fromkeys([*clean_tags, "配速法", branch_tag]))
            recommended = [
                topic_id
                for topic_id in _METHOD_KNOWLEDGE[branch]
                if topic_id in available_topic_ids
            ]
            topic_ids = list(dict.fromkeys([*recommended, *existing_topic_ids]))[:3]
        else:
            clean_tags = [tag for tag in clean_tags if tag != branch_tag]
            topic_ids = existing_topic_ids[:3]
        update: dict[str, Any] = {
            "question_id": clean_question_id,
            "tags": clean_tags,
        }
        if topic_ids:
            update.update(
                {
                    "topic3_ids": topic_ids,
                    "knowledge_source": "teacher_method_feedback",
                    "knowledge_confidences": [1.0] * len(topic_ids),
                    "knowledge_note": clean_reason or "教师方法检索反馈自动维护",
                }
            )
        metadata_result = MetadataManagementService(path).batch_update_question_metadata(
            [update],
            reason=clean_reason or f"教师确认{branch_tag}检索结果",
        )

    refresh_result = refresh_question_method_features([clean_question_id], db_path=path)
    return {
        "ok": True,
        "feedback_id": feedback_id,
        "question_id": clean_question_id,
        "method_id": method_id,
        "branch": branch,
        "verdict": verdict,
        "reason": clean_reason,
        "operator": clean_operator,
        "metadata_maintained": maintain_metadata,
        "metadata_result": metadata_result,
        "method_index_refresh": refresh_result,
    }


def list_method_retrieval_feedback(
    *,
    question_id: str | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = Path(db_path) if db_path else default_db_path()
    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        params: list[Any] = []
        where = ""
        if question_id:
            where = "WHERE question_id = ?"
            params.append(str(question_id).strip())
        params.append(min(max(int(limit), 1), 500))
        rows = conn.execute(
            f"""
            SELECT * FROM method_retrieval_feedback
            {where}
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
