from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path


QUESTION_TYPES = {"single_choice", "multi_choice", "fill", "experiment", "calculation"}
MAX_METADATA_UPDATES = 100
MAX_KNOWLEDGE_POINTS = 100
MAX_TAGS_PER_QUESTION = 20


class MetadataManagementService:
    """Autonomous maintenance of searchable question metadata."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else default_db_path()

    def create_knowledge_points(self, points: list[dict[str, Any]]) -> dict[str, Any]:
        if not points:
            return _error("INVALID_ARGUMENT", "points 至少需要一个知识点。", "points")
        if len(points) > MAX_KNOWLEDGE_POINTS:
            return _error("LIMIT_EXCEEDED", f"一次最多创建 {MAX_KNOWLEDGE_POINTS} 个知识点。", "points")

        created: list[dict[str, Any]] = []
        existing: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for index, raw in enumerate(points):
                    result = self._create_one_knowledge_point(conn, raw, index)
                    {"created": created, "existing": existing, "invalid": invalid}[result[0]].append(result[1])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "ok": not invalid,
            "created": created,
            "existing": existing,
            "invalid": invalid,
            "summary": {
                "received": len(points),
                "created": len(created),
                "existing": len(existing),
                "invalid": len(invalid),
            },
        }

    def suggest_knowledge_points(
        self,
        questions: list[dict[str, Any]],
        *,
        max_suggestions: int = 3,
    ) -> dict[str, Any]:
        limit = min(max(int(max_suggestions or 3), 1), 5)
        with closing(self._connect(writable=False)) as conn:
            rows = conn.execute(
                """
                SELECT topic3_id, topic3_name, topic2_id, topic2_name,
                       topic1_id, topic1_name, source_chapter
                FROM knowledge_points
                WHERE status = 'active'
                ORDER BY topic1_id, topic2_id, topic3_name
                """
            ).fetchall()
        points = [dict(row) for row in rows]
        matched: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []
        for index, question in enumerate(questions, start=1):
            qid = str(question.get("question_id") or question.get("id") or question.get("draft_id") or "").strip()
            title = str(question.get("title") or question.get("stem") or question.get("question_body") or "").strip()
            knowledge_hint = str(question.get("knowledge_point") or question.get("knowledge_points") or "").strip()
            corpus = _search_text(f"{title} {knowledge_hint}")
            ranked = sorted(
                (
                    (_knowledge_score(corpus, point), point)
                    for point in points
                ),
                key=lambda item: (-item[0], item[1]["topic3_id"]),
            )
            suggestions = [
                {
                    **point,
                    "confidence": _confidence(score),
                    "score": score,
                    "rationale": _knowledge_rationale(corpus, point, score),
                }
                for score, point in ranked[:limit]
                if score >= 18
            ]
            base = {
                "question_id": qid,
                "question_no": question.get("question_no") or index,
                "title_preview": " ".join(title.split())[:120],
            }
            if suggestions:
                matched.append({**base, "suggestions": suggestions})
            else:
                nearest = ranked[0][1] if ranked and ranked[0][0] > 0 else None
                unmatched.append(
                    {
                        **base,
                        "reason": "现有知识树中没有达到最低匹配阈值的知识点。",
                        "knowledge_hint": knowledge_hint,
                        "suggested_new_topic3_name": knowledge_hint or None,
                        "suggested_parent": (
                            {
                                "topic1_id": nearest["topic1_id"],
                                "topic1_name": nearest["topic1_name"],
                                "topic2_id": nearest["topic2_id"],
                                "topic2_name": nearest["topic2_name"],
                            }
                            if nearest is not None
                            else None
                        ),
                    }
                )
        return {
            "ok": True,
            "matched": matched,
            "unmatched": unmatched,
            "summary": {
                "total": len(questions),
                "matched": len(matched),
                "unmatched": len(unmatched),
                "knowledge_point_count": len(points),
            },
        }

    def batch_update_question_metadata(
        self,
        updates: list[dict[str, Any]],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not updates:
            return _error("INVALID_ARGUMENT", "updates 至少需要一项。", "updates")
        if len(updates) > MAX_METADATA_UPDATES:
            return _error("LIMIT_EXCEEDED", f"一次最多更新 {MAX_METADATA_UPDATES} 道题。", "updates")

        updated: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for index, raw in enumerate(updates):
                    savepoint = f"metadata_{index}"
                    conn.execute(f"SAVEPOINT {savepoint}")
                    try:
                        result = self._update_one_question_metadata(conn, raw, index)
                        conn.execute(f"RELEASE {savepoint}")
                        {"updated": updated, "skipped": skipped}[result[0]].append(result[1])
                    except ValueError as exc:
                        conn.execute(f"ROLLBACK TO {savepoint}")
                        conn.execute(f"RELEASE {savepoint}")
                        failed.append(
                            {
                                "index": index,
                                "question_id": str(raw.get("question_id") or "").strip(),
                                "error": str(exc),
                            }
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        clean_reason = " ".join(str(reason or "").split())[:300] or None
        return {
            "ok": not failed,
            "reason": clean_reason,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "summary": {
                "received": len(updates),
                "updated": len(updated),
                "skipped": len(skipped),
                "failed": len(failed),
            },
        }

    def _connect(self, *, writable: bool = True) -> sqlite3.Connection:
        if not self._db_path.is_file():
            raise FileNotFoundError(f"正式题库数据库不存在：{self._db_path}")
        return connect_db(self._db_path, writable=writable)

    def _create_one_knowledge_point(
        self,
        conn: sqlite3.Connection,
        raw: dict[str, Any],
        index: int,
    ) -> tuple[str, dict[str, Any]]:
        topic1_id = str(raw.get("topic1_id") or "").strip()
        topic1_name = str(raw.get("topic1_name") or "").strip()
        topic2_id = str(raw.get("topic2_id") or "").strip()
        topic2_name = str(raw.get("topic2_name") or "").strip()
        topic3_id = str(raw.get("topic3_id") or "").strip()
        topic3_name = str(raw.get("topic3_name") or "").strip()
        source_chapter = str(raw.get("source_chapter") or "").strip() or None
        if not topic1_id or not topic3_name:
            return "invalid", {"index": index, "reason": "topic1_id 和 topic3_name 不能为空。"}

        hierarchy = conn.execute(
            """
            SELECT topic1_name, topic2_id, topic2_name
            FROM knowledge_points
            WHERE topic1_id = ?
            ORDER BY topic3_id
            """,
            (topic1_id,),
        ).fetchall()
        if hierarchy and not topic1_name:
            topic1_name = str(hierarchy[0]["topic1_name"])
        if not topic1_name:
            return "invalid", {"index": index, "reason": "新的一级知识点必须提供 topic1_name。"}

        if topic2_id:
            parent = next((row for row in hierarchy if row["topic2_id"] == topic2_id), None)
            if parent is not None:
                topic2_name = str(parent["topic2_name"])
            elif not topic2_name:
                return "invalid", {"index": index, "reason": f"新的 topic2_id 必须同时提供 topic2_name：{topic2_id}"}
            else:
                conflicting_parent = conn.execute(
                    "SELECT topic1_id FROM knowledge_points WHERE topic2_id = ? LIMIT 1",
                    (topic2_id,),
                ).fetchone()
                if conflicting_parent is not None and conflicting_parent["topic1_id"] != topic1_id:
                    return "invalid", {"index": index, "reason": f"topic2_id 已属于其他一级目录：{topic2_id}"}
        else:
            parent = next((row for row in hierarchy if _name_key(row["topic2_name"]) == _name_key(topic2_name)), None)
            if parent is not None:
                topic2_id = str(parent["topic2_id"])
                topic2_name = str(parent["topic2_name"])
            elif topic2_name:
                topic2_id = _stable_id(topic1_id, "L2", topic2_name)
            else:
                return "invalid", {"index": index, "reason": "未指定 topic2_id 时必须提供 topic2_name。"}

        same_name = conn.execute(
            """
            SELECT * FROM knowledge_points
            WHERE topic2_id = ? AND lower(trim(topic3_name)) = lower(trim(?))
            """,
            (topic2_id, topic3_name),
        ).fetchone()
        if same_name is not None:
            return "existing", dict(same_name)

        topic3_id = topic3_id or _stable_id(topic2_id, "L3", topic3_name)
        same_id = conn.execute("SELECT * FROM knowledge_points WHERE topic3_id = ?", (topic3_id,)).fetchone()
        if same_id is not None:
            if _name_key(same_id["topic3_name"]) == _name_key(topic3_name):
                return "existing", dict(same_id)
            return "invalid", {"index": index, "reason": f"topic3_id 已被其他知识点占用：{topic3_id}"}

        conn.execute(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name,
                topic1_id, topic1_name, source_chapter, status, note,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name, source_chapter),
        )
        return "created", {
            "topic3_id": topic3_id,
            "topic3_name": topic3_name,
            "topic2_id": topic2_id,
            "topic2_name": topic2_name,
            "topic1_id": topic1_id,
            "topic1_name": topic1_name,
            "source_chapter": source_chapter,
        }

    def _update_one_question_metadata(
        self,
        conn: sqlite3.Connection,
        raw: dict[str, Any],
        index: int,
    ) -> tuple[str, dict[str, Any]]:
        question_id = str(raw.get("question_id") or "").strip()
        if not question_id:
            raise ValueError(f"第 {index + 1} 项缺少 question_id。")
        question = conn.execute(
            "SELECT question_id, primary_paper_id FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if question is None:
            raise ValueError("正式题库中不存在该题。")

        allowed = {
            "question_id", "tags", "topic3_ids", "difficulty", "question_type",
            "source_normalized", "year", "region", "exam_type",
        }
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ValueError(f"包含不允许修改的字段：{', '.join(unknown)}。")

        changes: dict[str, Any] = {}
        question_sets: list[str] = []
        question_params: list[Any] = []
        if "difficulty" in raw and raw.get("difficulty") is not None:
            difficulty = int(raw["difficulty"])
            if difficulty < 1 or difficulty > 5:
                raise ValueError("difficulty 必须在 1 到 5 之间。")
            question_sets.append("difficulty = ?")
            question_params.append(difficulty)
            changes["difficulty"] = difficulty
        if "question_type" in raw and raw.get("question_type") is not None:
            question_type = str(raw["question_type"]).strip()
            if question_type not in QUESTION_TYPES:
                raise ValueError(f"不支持的 question_type：{question_type}")
            question_sets.append("question_type = ?")
            question_params.append(question_type)
            changes["question_type"] = question_type
        if "source_normalized" in raw and raw.get("source_normalized") is not None:
            source = " ".join(str(raw["source_normalized"]).split())[:300]
            question_sets.append("source = ?")
            question_params.append(source)
            changes["source_normalized"] = source
        if question_sets:
            question_params.append(question_id)
            conn.execute(
                f"UPDATE questions SET {', '.join(question_sets)}, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                question_params,
            )

        if "tags" in raw and raw.get("tags") is not None:
            tags = _normalize_tags(raw.get("tags"))
            conn.execute(
                """
                INSERT INTO question_text_index (question_id, tags_json, created_at, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id) DO UPDATE SET
                    tags_json = excluded.tags_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (question_id, json.dumps(tags, ensure_ascii=False)),
            )
            changes["tags"] = tags

        if "topic3_ids" in raw and raw.get("topic3_ids") is not None:
            topic3_ids = list(dict.fromkeys(str(item).strip() for item in raw.get("topic3_ids") or [] if str(item).strip()))
            if len(topic3_ids) > 3:
                raise ValueError("每道题最多绑定 3 个知识点。")
            points: dict[str, sqlite3.Row] = {}
            if topic3_ids:
                placeholders = ",".join("?" for _ in topic3_ids)
                rows = conn.execute(
                    f"SELECT * FROM knowledge_points WHERE status = 'active' AND topic3_id IN ({placeholders})",
                    topic3_ids,
                ).fetchall()
                points = {str(row["topic3_id"]): row for row in rows}
                missing = [item for item in topic3_ids if item not in points]
                if missing:
                    raise ValueError(f"知识点不存在：{', '.join(missing)}")
            conn.execute("DELETE FROM question_knowledge_points WHERE question_id = ?", (question_id,))
            for rank, topic3_id in enumerate(topic3_ids, start=1):
                conn.execute(
                    """
                    INSERT INTO question_knowledge_points (
                        link_id, question_id, topic3_id, rank, source, confidence,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'ai_metadata', 1.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (f"QKP-{question_id}-{rank}-{hashlib.sha256(topic3_id.encode()).hexdigest()[:8]}", question_id, topic3_id, rank),
                )
            primary = points.get(topic3_ids[0]) if topic3_ids else None
            conn.execute(
                """
                UPDATE questions
                SET module = ?, topic2 = ?, topic3 = ?, updated_at = CURRENT_TIMESTAMP
                WHERE question_id = ?
                """,
                (
                    primary["topic1_name"] if primary else None,
                    primary["topic2_name"] if primary else None,
                    primary["topic3_name"] if primary else None,
                    question_id,
                ),
            )
            changes["topic3_ids"] = topic3_ids

        paper_fields: dict[str, Any] = {}
        if "year" in raw and raw.get("year") is not None:
            try:
                year = int(raw["year"])
            except (TypeError, ValueError) as exc:
                raise ValueError("year 必须是有效年份。") from exc
            if year < 1900 or year > 2100:
                raise ValueError("year 必须在 1900 到 2100 之间。")
            paper_fields["year"] = year
        for field in ("region", "exam_type"):
            if field not in raw or raw.get(field) is None:
                continue
            value = " ".join(str(raw[field]).split())
            if not value:
                raise ValueError(f"{field} 不能为空字符串。")
            if len(value) > 50:
                raise ValueError(f"{field} 不能超过 50 个字符。")
            paper_fields[field] = value
        if paper_fields:
            paper_id = str(question["primary_paper_id"] or "").strip()
            if not paper_id:
                raise ValueError("题目没有关联试卷，无法更新年份、地区或试卷类型。")
            assignments = [f"{key} = ?" for key in paper_fields]
            values = list(paper_fields.values()) + [paper_id]
            conn.execute(
                f"UPDATE papers SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP WHERE paper_id = ?",
                values,
            )
            changes.update(paper_fields)

        if not changes:
            return "skipped", {"question_id": question_id, "reason": "没有提供可更新字段。"}
        return "updated", {"question_id": question_id, "changes": changes}


def _stable_id(parent_id: str, level: str, name: str) -> str:
    digest = hashlib.sha256(f"{parent_id}\0{_name_key(name)}".encode("utf-8")).hexdigest()[:10].upper()
    return f"{parent_id}-{level}-{digest}"


def _name_key(value: Any) -> str:
    return re.sub(r"[\s·•,，、。:：;；()（）\-_]+", "", str(value or "")).casefold()


def _search_text(value: Any) -> str:
    return _name_key(value)


def _bigrams(value: str) -> set[str]:
    if len(value) < 2:
        return {value} if value else set()
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _knowledge_score(corpus: str, point: dict[str, Any]) -> int:
    topic3 = _search_text(point.get("topic3_name"))
    topic2 = _search_text(point.get("topic2_name"))
    topic1 = _search_text(point.get("topic1_name"))
    if topic3 and topic3 in corpus:
        return 100
    score = 0
    for value, weight in ((topic3, 70), (topic2, 35), (topic1, 15)):
        if not value:
            continue
        if value in corpus:
            score = max(score, weight)
        source_pairs = _bigrams(corpus)
        value_pairs = _bigrams(value)
        if value_pairs:
            overlap = len(source_pairs & value_pairs) / len(value_pairs)
            score = max(score, round(weight * overlap))
    return score


def _confidence(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _knowledge_rationale(corpus: str, point: dict[str, Any], score: int) -> str:
    topic3 = str(point.get("topic3_name") or "")
    if _search_text(topic3) in corpus:
        return f"题目文本直接包含“{topic3}”。"
    return f"题目文本与“{topic3}”及其上级目录存在关键词重合，规则匹配分为 {score}。"


def _normalize_tags(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace("，", ",").replace("、", ",").split(",")
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tag = " ".join(str(item).split())[:30]
        key = tag.casefold()
        if not tag or key in seen:
            continue
        seen.add(key)
        result.append(tag)
        if len(result) >= MAX_TAGS_PER_QUESTION:
            break
    return result


def _error(code: str, message: str, field: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "error_info": {
            "code": code,
            "message": message,
            "retryable": False,
            "details": {"field": field},
        },
    }
