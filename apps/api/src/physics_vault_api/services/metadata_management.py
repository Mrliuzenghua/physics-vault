from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path
from .embedding_refresh import schedule_question_embedding_refresh
from .method_feature_index import refresh_question_method_features


QUESTION_TYPES = {"single_choice", "multi_choice", "fill", "experiment", "calculation"}
MAX_METADATA_UPDATES = 100
MAX_KNOWLEDGE_POINTS = 100
MAX_TAGS_PER_QUESTION = 20
MAX_KNOWLEDGE_POINTS_PER_QUESTION = 3
KNOWLEDGE_SUGGESTION_THRESHOLD = 18
KNOWLEDGE_AUTO_FIX_THRESHOLD = 80


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
        limit = min(max(int(max_suggestions or 3), 1), MAX_KNOWLEDGE_POINTS_PER_QUESTION)
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

    def diagnose_question_knowledge_points(
        self,
        question_ids: list[str],
        *,
        max_suggestions: int = MAX_KNOWLEDGE_POINTS_PER_QUESTION,
    ) -> dict[str, Any]:
        """Compare canonical bindings with evidence from the question itself.

        Existing labels are deliberately excluded from the evidence corpus so a
        stale label cannot confirm itself. Automatic repairs are recommended only
        for high-confidence direct matches; ambiguous cases remain review-only.
        """

        clean_ids = list(dict.fromkeys(str(item or "").strip() for item in question_ids if str(item or "").strip()))
        if not clean_ids:
            return _error("INVALID_ARGUMENT", "question_ids 至少需要一个题号。", "question_ids")
        if len(clean_ids) > MAX_METADATA_UPDATES:
            return _error("LIMIT_EXCEEDED", f"一次最多诊断 {MAX_METADATA_UPDATES} 道题。", "question_ids")
        limit = min(max(int(max_suggestions or MAX_KNOWLEDGE_POINTS_PER_QUESTION), 1), MAX_KNOWLEDGE_POINTS_PER_QUESTION)
        placeholders = ",".join("?" for _ in clean_ids)
        with closing(self._connect(writable=False)) as conn:
            point_rows = conn.execute(
                """
                SELECT topic3_id, topic3_name, topic2_id, topic2_name,
                       topic1_id, topic1_name, source_chapter
                FROM knowledge_points
                WHERE status = 'active'
                ORDER BY topic1_id, topic2_id, topic3_name
                """
            ).fetchall()
            question_rows = conn.execute(
                f"""
                SELECT q.question_id, q.canonical_title, qti.title_text, qti.stem_text,
                       qti.stem_clean_text, qti.analysis_text
                FROM questions q
                LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
                WHERE q.question_id IN ({placeholders})
                """,
                clean_ids,
            ).fetchall()
            binding_rows = conn.execute(
                f"""
                SELECT question_id, rank, topic3_id, topic3_name, topic2_id,
                       topic2_name, topic1_id, topic1_name, source, confidence, note
                FROM question_knowledge_points_view
                WHERE question_id IN ({placeholders})
                ORDER BY question_id, rank, topic3_id
                """,
                clean_ids,
            ).fetchall()

        points = [dict(row) for row in point_rows]
        questions = {str(row["question_id"]): dict(row) for row in question_rows}
        current_by_question: dict[str, list[dict[str, Any]]] = {qid: [] for qid in clean_ids}
        for row in binding_rows:
            current_by_question.setdefault(str(row["question_id"]), []).append(dict(row))

        items: list[dict[str, Any]] = []
        missing_ids: list[str] = []
        safe_updates: list[dict[str, Any]] = []
        for question_id in clean_ids:
            question = questions.get(question_id)
            if question is None:
                missing_ids.append(question_id)
                continue
            evidence_text = " ".join(
                str(question.get(key) or "")
                for key in ("canonical_title", "title_text", "stem_clean_text", "stem_text", "analysis_text")
            )
            corpus = _search_text(evidence_text)
            ranked = sorted(
                ((_knowledge_score(corpus, point), point) for point in points),
                key=lambda item: (-item[0], item[1]["topic3_id"]),
            )
            suggestions = [
                {
                    **point,
                    "score": score,
                    "confidence": _confidence(score),
                    "rationale": _knowledge_rationale(corpus, point, score),
                }
                for score, point in ranked
                if score >= KNOWLEDGE_SUGGESTION_THRESHOLD
            ][:limit]
            current = current_by_question.get(question_id, [])
            current_ids = [str(point["topic3_id"]) for point in current]
            score_by_id = {str(point["topic3_id"]): score for score, point in ranked}
            current_with_evidence = [
                {**point, "evidence_score": score_by_id.get(str(point["topic3_id"]), 0)}
                for point in current
            ]
            suggested_ids = [str(point["topic3_id"]) for point in suggestions]
            strong_ids = [
                str(point["topic3_id"])
                for point in suggestions
                if int(point["score"]) >= 45
            ][:MAX_KNOWLEDGE_POINTS_PER_QUESTION]
            top_score = int(suggestions[0]["score"]) if suggestions else 0
            primary_score = score_by_id.get(current_ids[0], 0) if current_ids else 0

            if not current_ids:
                status = "missing"
            elif top_score >= KNOWLEDGE_AUTO_FIX_THRESHOLD and suggested_ids[0] not in current_ids and primary_score < 45:
                status = "suspected_mismatch"
            elif len(current_ids) < MAX_KNOWLEDGE_POINTS_PER_QUESTION and any(item not in current_ids for item in strong_ids):
                status = "incomplete"
            elif primary_score < KNOWLEDGE_SUGGESTION_THRESHOLD and top_score >= 45:
                status = "needs_review"
            else:
                status = "healthy"

            if status == "incomplete":
                recommended_ids = list(dict.fromkeys([*current_ids, *strong_ids]))[:MAX_KNOWLEDGE_POINTS_PER_QUESTION]
            elif status in {"missing", "suspected_mismatch"}:
                recommended_ids = strong_ids
            else:
                recommended_ids = current_ids
            auto_fix_safe = (
                status in {"missing", "suspected_mismatch", "incomplete"}
                and top_score >= KNOWLEDGE_AUTO_FIX_THRESHOLD
                and bool(recommended_ids)
                and recommended_ids != current_ids
            )
            item = {
                "question_id": question_id,
                "title_preview": " ".join(str(question.get("title_text") or question.get("canonical_title") or "").split())[:160],
                "status": status,
                "current": current_with_evidence,
                "suggestions": suggestions,
                "recommended_topic3_ids": recommended_ids,
                "target_count": MAX_KNOWLEDGE_POINTS_PER_QUESTION,
                "auto_fix_safe": auto_fix_safe,
                "reason": (
                    "题目正文直接命中了新的三级知识点，且当前主知识点缺少文本证据。"
                    if status == "suspected_mismatch"
                    else "题目还有证据充分的辅助知识点，可补充到最多三个。"
                    if status == "incomplete"
                    else "题目尚未绑定知识点。"
                    if status == "missing"
                    else "现有绑定与题目证据基本一致。"
                    if status == "healthy"
                    else "现有绑定证据较弱，但自动修改的置信度不足。"
                ),
            }
            items.append(item)
            if auto_fix_safe:
                confidence_by_id = {str(point["topic3_id"]): min(float(point["score"]) / 100.0, 1.0) for point in suggestions}
                safe_updates.append(
                    {
                        "question_id": question_id,
                        "topic3_ids": recommended_ids,
                        "knowledge_source": "agent_maintenance",
                        "knowledge_confidences": [confidence_by_id.get(topic3_id, 0.75) for topic3_id in recommended_ids],
                        "knowledge_note": "智能体根据题干与解析进行高置信度知识点维护",
                    }
                )

        return {
            "ok": True,
            "items": items,
            "missing_question_ids": missing_ids,
            "safe_updates": safe_updates,
            "summary": {
                "requested": len(clean_ids),
                "diagnosed": len(items),
                "missing_questions": len(missing_ids),
                "healthy": sum(item["status"] == "healthy" for item in items),
                "incomplete": sum(item["status"] == "incomplete" for item in items),
                "suspected_mismatch": sum(item["status"] == "suspected_mismatch" for item in items),
                "needs_review": sum(item["status"] == "needs_review" for item in items),
                "safe_fix_count": len(safe_updates),
            },
        }

    def maintain_question_knowledge_points(
        self,
        question_ids: list[str],
        *,
        auto_fix: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any]:
        diagnosis = self.diagnose_question_knowledge_points(question_ids)
        if not diagnosis.get("ok") or not auto_fix or not diagnosis.get("safe_updates"):
            return {**diagnosis, "auto_fix": auto_fix, "repair": None}
        repair = self.batch_update_question_metadata(
            diagnosis["safe_updates"],
            reason=reason or "智能体检索后自动维护高置信度知识点绑定",
        )
        return {**diagnosis, "auto_fix": True, "repair": repair}

    def search_knowledge_points(
        self,
        keyword: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return fuzzy-ranked knowledge points for Chinese queries."""

        corpus = _search_query_text(keyword)
        if not corpus:
            return []
        bounded_limit = min(max(int(limit or 20), 1), 100)
        with closing(self._connect(writable=False)) as conn:
            rows = conn.execute(
                """
                SELECT topic3_id, topic3_name, topic2_id, topic2_name,
                       topic1_id, topic1_name, source_chapter, status, note
                FROM knowledge_points
                WHERE status = 'active'
                ORDER BY topic1_id, topic2_id, topic3_name
                """
            ).fetchall()
        ranked = sorted(
            ((_knowledge_score(corpus, dict(row)), dict(row)) for row in rows),
            key=lambda item: (-item[0], item[1]["topic3_id"]),
        )
        return [
            {
                **point,
                "score": score,
                "confidence": _confidence(score),
                "rationale": _knowledge_rationale(corpus, point, score),
            }
            for score, point in ranked[:bounded_limit]
            if score >= 12
        ]

    def organize_knowledge_tree(
        self,
        assignments: list[dict[str, Any]],
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create missing nodes and bind formal questions in one transaction.

        Draft question IDs are returned as structured patches. The MCP layer can
        apply those patches to a review task without requiring a second AI pass.
        """

        if not assignments:
            return _error("INVALID_ARGUMENT", "assignments must contain at least one item.", "assignments")
        if len(assignments) > MAX_METADATA_UPDATES:
            return _error(
                "LIMIT_EXCEEDED",
                f"At most {MAX_METADATA_UPDATES} assignments can be organized at once.",
                "assignments",
            )

        created: list[dict[str, Any]] = []
        existing: list[dict[str, Any]] = []
        bound: list[dict[str, Any]] = []
        draft_updates: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for index, assignment in enumerate(assignments):
                    question_id = str(
                        assignment.get("question_id") or assignment.get("id") or ""
                    ).strip()
                    raw_points = assignment.get("knowledge_points") or []
                    if isinstance(raw_points, dict):
                        raw_points = [raw_points]
                    if not question_id or not isinstance(raw_points, list) or not raw_points:
                        failed.append(
                            {
                                "index": index,
                                "question_id": question_id,
                                "error": "question_id and knowledge_points are required.",
                            }
                        )
                        continue
                    if len(raw_points) > MAX_KNOWLEDGE_POINTS_PER_QUESTION:
                        failed.append(
                            {
                                "index": index,
                                "question_id": question_id,
                                "error": f"每道题最多绑定 {MAX_KNOWLEDGE_POINTS_PER_QUESTION} 个三级知识点。",
                            }
                        )
                        continue

                    resolved: list[dict[str, Any]] = []
                    for point_index, raw_point in enumerate(raw_points):
                        if not isinstance(raw_point, dict):
                            failed.append(
                                {
                                    "index": index,
                                    "question_id": question_id,
                                    "error": f"knowledge_points[{point_index}] must be an object.",
                                }
                            )
                            continue
                        result_kind, result_point = self._create_one_knowledge_point(
                            conn, raw_point, point_index
                        )
                        if result_kind == "invalid":
                            failed.append(
                                {
                                    "index": index,
                                    "question_id": question_id,
                                    "error": result_point.get("reason") or "Invalid knowledge point.",
                                }
                            )
                            continue
                        resolved.append(result_point)
                        (created if result_kind == "created" else existing).append(result_point)

                    topic3_ids = list(
                        dict.fromkeys(str(point["topic3_id"]) for point in resolved)
                    )
                    if not topic3_ids:
                        continue
                    primary = resolved[0]
                    patch: dict[str, Any] = {
                        "question_id": question_id,
                        "knowledge_point": primary["topic3_name"],
                        "knowledge_points": resolved,
                        "topic3_ids": topic3_ids,
                        "topic1_id": primary["topic1_id"],
                        "topic1_name": primary["topic1_name"],
                        "topic2_id": primary["topic2_id"],
                        "topic2_name": primary["topic2_name"],
                        "topic3_id": primary["topic3_id"],
                        "topic3_name": primary["topic3_name"],
                    }
                    for field in ("year", "tags", "source"):
                        if field in assignment and assignment.get(field) is not None:
                            patch[field] = assignment[field]

                    formal = conn.execute(
                        "SELECT primary_paper_id FROM questions WHERE question_id = ?",
                        (question_id,),
                    ).fetchone()
                    if formal is None:
                        draft_updates.append(patch)
                        continue

                    metadata_update: dict[str, Any] = {
                        "question_id": question_id,
                        "topic3_ids": topic3_ids,
                    }
                    if "tags" in patch:
                        metadata_update["tags"] = patch["tags"]
                    if "source" in patch:
                        metadata_update["source_normalized"] = patch["source"]
                    if "year" in patch and str(formal["primary_paper_id"] or "").strip():
                        metadata_update["year"] = patch["year"]
                    elif "year" in patch:
                        warnings.append(
                            {
                                "question_id": question_id,
                                "field": "year",
                                "message": "The question has no linked paper, so year was kept out of the formal metadata update.",
                            }
                        )
                    _, update_result = self._update_one_question_metadata(
                        conn, metadata_update, index
                    )
                    bound.append(update_result)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {
            "ok": not failed,
            "reason": " ".join(str(reason or "").split())[:300] or None,
            "created": _dedupe_points(created),
            "existing": _dedupe_points(existing),
            "bound": bound,
            "draft_updates": draft_updates,
            "failed": failed,
            "warnings": warnings,
            "summary": {
                "received": len(assignments),
                "created": len(_dedupe_points(created)),
                "reused": len(_dedupe_points(existing)),
                "bound": len(bound),
                "draft_updates": len(draft_updates),
                "failed": len(failed),
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
        audit_batch_id: str | None = None
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
                audit_batch_id = _record_knowledge_binding_audit(conn, updated, reason)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        clean_reason = " ".join(str(reason or "").split())[:300] or None
        schedule_question_embedding_refresh(
            [str(item["question_id"]) for item in updated],
            db_path=self._db_path,
        )
        refresh_question_method_features(
            [str(item["question_id"]) for item in updated],
            db_path=self._db_path,
        )
        return {
            "ok": not failed,
            "reason": clean_reason,
            "audit_batch_id": audit_batch_id,
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

        same_name_rows = conn.execute(
            """
            SELECT * FROM knowledge_points
            WHERE topic2_id = ?
            """,
            (topic2_id,),
        ).fetchall()
        same_name = next(
            (
                row
                for row in same_name_rows
                if _name_key(row["topic3_name"]) == _name_key(topic3_name)
            ),
            None,
        )
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
            "source_normalized", "primary_paper_id", "year", "region", "exam_type",
            "knowledge_source", "knowledge_confidences", "knowledge_note",
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
        effective_paper_id = str(question["primary_paper_id"] or "").strip()
        if "primary_paper_id" in raw and raw.get("primary_paper_id") is not None:
            primary_paper_id = str(raw["primary_paper_id"]).strip()
            if not primary_paper_id:
                raise ValueError("primary_paper_id 不能为空；如需解除关联，请使用专门的解绑流程。")
            paper = conn.execute(
                "SELECT paper_id FROM papers WHERE paper_id = ?",
                (primary_paper_id,),
            ).fetchone()
            if paper is None:
                raise ValueError(f"正式题库中不存在试卷：{primary_paper_id}")
            effective_paper_id = primary_paper_id
            question_sets.append("primary_paper_id = ?")
            question_params.append(primary_paper_id)
            changes["primary_paper_id"] = primary_paper_id
        if question_sets:
            question_params.append(question_id)
            conn.execute(
                f"UPDATE questions SET {', '.join(question_sets)}, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                question_params,
            )
        if "primary_paper_id" in raw and raw.get("primary_paper_id") is not None:
            conn.execute(
                "UPDATE question_text_index SET paper_id = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (effective_paper_id, question_id),
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
            if len(topic3_ids) > MAX_KNOWLEDGE_POINTS_PER_QUESTION:
                raise ValueError(f"每道题最多绑定 {MAX_KNOWLEDGE_POINTS_PER_QUESTION} 个三级知识点。")
            before_topic3_ids = [
                str(row["topic3_id"])
                for row in conn.execute(
                    "SELECT topic3_id FROM question_knowledge_points WHERE question_id = ? ORDER BY rank, topic3_id",
                    (question_id,),
                ).fetchall()
            ]
            knowledge_source = str(raw.get("knowledge_source") or "ai_metadata").strip()[:50] or "ai_metadata"
            confidence_values = raw.get("knowledge_confidences")
            if confidence_values is None:
                confidences = [1.0] * len(topic3_ids)
            elif isinstance(confidence_values, (int, float)):
                confidences = [float(confidence_values)] * len(topic3_ids)
            elif isinstance(confidence_values, list) and len(confidence_values) == len(topic3_ids):
                confidences = [float(value) for value in confidence_values]
            else:
                raise ValueError("knowledge_confidences 必须与 topic3_ids 数量一致。")
            if any(value < 0 or value > 1 for value in confidences):
                raise ValueError("knowledge_confidences 必须在 0 到 1 之间。")
            knowledge_note = " ".join(str(raw.get("knowledge_note") or "").split())[:500] or None
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
                        link_id, question_id, topic3_id, rank, source, confidence, note,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"QKP-{question_id}-{rank}-{hashlib.sha256(topic3_id.encode()).hexdigest()[:8]}",
                        question_id,
                        topic3_id,
                        rank,
                        knowledge_source,
                        confidences[rank - 1],
                        knowledge_note,
                    ),
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
            changes["knowledge_source"] = knowledge_source
            changes["knowledge_confidences"] = confidences
            if knowledge_note:
                changes["knowledge_note"] = knowledge_note
            changes["previous_topic3_ids"] = before_topic3_ids

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
            paper_id = effective_paper_id
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
        if {"topic3_ids", "difficulty", "question_type"} & changes.keys():
            conn.execute(
                """
                UPDATE embeddings
                SET status = 'stale', updated_at = CURRENT_TIMESTAMP
                WHERE owner_type = 'question' AND owner_id = ?
                """,
                (question_id,),
            )
        return "updated", {"question_id": question_id, "changes": changes}


def _stable_id(parent_id: str, level: str, name: str) -> str:
    digest = hashlib.sha256(f"{parent_id}\0{_name_key(name)}".encode("utf-8")).hexdigest()[:10].upper()
    return f"{parent_id}-{level}-{digest}"


def _name_key(value: Any) -> str:
    return re.sub(r"[\s·•,，、。:：;；()（）\-_]+", "", str(value or "")).casefold()


def _search_text(value: Any) -> str:
    return _name_key(value)


def _search_query_text(value: Any) -> str:
    normalized = _search_text(value)
    aliases = {
        "\u53c2\u8003\u7cfb": "\u53c2\u8003\u7cfb\u76f8\u5bf9\u8fd0\u52a8\u8fd0\u52a8\u7684\u5408\u6210\u4e0e\u5206\u89e3",
        "\u76f8\u5bf9\u8fd0\u52a8": "\u76f8\u5bf9\u8fd0\u52a8\u53c2\u8003\u7cfb\u8fd0\u52a8\u7684\u5408\u6210\u4e0e\u5206\u89e3",
        "cankaoxi": "\u53c2\u8003\u7cfb\u76f8\u5bf9\u8fd0\u52a8\u8fd0\u52a8\u7684\u5408\u6210\u4e0e\u5206\u89e3",
        "xiangduiyundong": "\u76f8\u5bf9\u8fd0\u52a8\u53c2\u8003\u7cfb\u8fd0\u52a8\u7684\u5408\u6210\u4e0e\u5206\u89e3",
        "参考系": "参照物参考系",
        "参照物": "参考系参照物",
        "卫星轨道": "人造卫星圆周运动轨道",
        "磁感应强度": "磁场磁感应强度",
        "平抛运动": "抛体运动平抛运动",
        "宇宙速度": "人造卫星宇宙速度",
    }
    if normalized in {"\u53c2\u8003\u7cfb", "cankaoxi"}:
        return "\u53c2\u8003\u7cfb\u76f8\u5bf9\u8fd0\u52a8\u8fd0\u52a8\u7684\u5408\u6210\u4e0e\u5206\u89e3"
    if normalized in {"\u76f8\u5bf9\u8fd0\u52a8", "xiangduiyundong"}:
        return "\u76f8\u5bf9\u8fd0\u52a8\u53c2\u8003\u7cfb\u8fd0\u52a8\u7684\u5408\u6210\u4e0e\u5206\u89e3"
    return aliases.get(normalized, normalized)


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


def _dedupe_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for point in points:
        topic3_id = str(point.get("topic3_id") or "").strip()
        if topic3_id:
            unique.setdefault(topic3_id, point)
    return list(unique.values())


def _record_knowledge_binding_audit(
    conn: sqlite3.Connection,
    updated: list[dict[str, Any]],
    reason: str | None,
) -> str | None:
    items = []
    for result in updated:
        changes = result.get("changes") if isinstance(result.get("changes"), dict) else {}
        if "topic3_ids" not in changes:
            continue
        before = [str(item) for item in changes.get("previous_topic3_ids") or []]
        after = [str(item) for item in changes.get("topic3_ids") or []]
        if before == after:
            continue
        items.append({"question_id": str(result.get("question_id") or ""), "before": before, "after": after})
    if not items:
        return None

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
            applied_at TEXT,
            rolled_back_at TEXT,
            rollback_reason TEXT
        )
        """
    )
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
    batch_id = f"CHG-{uuid.uuid4().hex[:12]}"
    conn.execute(
        """
        INSERT INTO change_batches (
            batch_id, change_type, reason, source, status,
            target_count, changed_count, applied_at
        ) VALUES (?, 'knowledge_binding_normalization', ?, 'agent_metadata_maintenance',
                  'applied', ?, ?, CURRENT_TIMESTAMP)
        """,
        (batch_id, " ".join(str(reason or "").split())[:300] or None, len(items), len(items)),
    )
    for item in items:
        conn.execute(
            """
            INSERT INTO change_items (
                item_id, batch_id, entity_type, entity_id, field_name,
                before_value_json, after_value_json, status, risk_level
            ) VALUES (?, ?, 'question', ?, 'question_knowledge_points.topic3_id',
                      ?, ?, 'changed', 'medium')
            """,
            (
                f"CHI-{uuid.uuid4().hex[:12]}",
                batch_id,
                item["question_id"],
                json.dumps(item["before"], ensure_ascii=False),
                json.dumps(item["after"], ensure_ascii=False),
            ),
        )
    return batch_id


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
