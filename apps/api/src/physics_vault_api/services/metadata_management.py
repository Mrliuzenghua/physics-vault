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
# A knowledge binding changes search behaviour materially.  Keyword overlap is
# useful for triage, but not enough to replace an existing teacher-facing
# classification.  Automatic writes are therefore reserved for an entirely
# missing binding with an almost exact match; corrections and extra secondary
# points always remain review-only.
KNOWLEDGE_AUTO_FIX_THRESHOLD = 95

# Topic names in the taxonomy are intentionally concise, while exam questions
# often use a phenomenon, apparatus or classroom nickname instead.  These cues
# bridge that vocabulary gap without inventing new topic ids.  Scores below the
# auto-fix threshold keep alias matches review-only.
KNOWLEDGE_CONCEPT_CUES: dict[str, tuple[tuple[str, int], ...]] = {
    "天然放射现象": (("半衰期", 94), ("放射性", 92), ("α衰变", 94), ("β衰变", 94), ("伽马射线", 90), ("γ射线", 90)),
    "物理学史与科学方法": (("控制变量", 94), ("科学方法", 92), ("研究方案", 82)),
    "物理量、单位与测量": (("估算", 88), ("曝光时间", 92), ("有效数字", 92), ("测量误差", 94)),
    "机械波的传播": (("简谐横波", 94), ("波速", 92), ("波长", 88), ("波的传播", 94), ("质点振动", 86)),
    "波形图与振动图像": (("波形图", 94), ("波形曲线", 92), ("振动图像", 94), ("振动曲线", 92)),
    "抛体运动": (("平抛", 94), ("斜抛", 94), ("抛物线轨迹", 90)),
    "匀变速直线运动": (("速度时间图像", 92), ("位移时间图像", 90), ("v-t图像", 92), ("x-t图像", 90)),
    "万有引力定律": (("中心天体", 88), ("黑洞", 90), ("开普勒", 88), ("引力提供向心力", 92)),
    "卫星轨道": (("人造卫星", 94), ("环绕速度", 90), ("椭圆轨道", 86)),
    "电流与电阻定律": (("伏安特性", 94), ("伏安特性曲线", 94), ("电阻率", 90)),
    "测量电阻与电源电动势": (("多用电表", 90), ("欧姆表", 92), ("测电阻", 90), ("测电动势", 92)),
    "串并联电路": (("串联电路", 92), ("并联电路", 92), ("限流接法", 86), ("分压接法", 88)),
    "电势能与电势": (("等势面", 94), ("电势差", 92), ("电势能", 94)),
    "电场强度": (("电场线", 92), ("试探电荷", 88), ("电场力", 86), ("场强", 94)),
    "电容器": (("平行板电容", 94), ("电容", 90)),
    "光的波粒二象性": (("光子", 94), ("光量子", 94), ("普朗克常量", 92), ("光子数", 94)),
    "狭义相对论基本假设": (("光速不变", 94), ("惯性参考系", 92), ("真空中的光速", 94)),
    "LC振荡回路": (("LC振荡", 94), ("振荡电路", 92), ("接收电路", 88), ("固有频率", 88)),
    "分子动能与势能": (("分子势能", 94), ("分子间作用力", 92), ("分子距离", 84)),
    "折射定律": (("折射率", 94), ("入射角", 86), ("折射角", 90), ("三棱镜", 86)),
    "全反射": (("临界角", 94), ("没有光线射出", 88), ("恰好不射出", 90)),
    "理想气体状态方程": (("一定量的理想气体", 94), ("气缸", 84), ("活塞", 82)),
    "碰撞": (("碰撞过程", 94), ("碰撞结束", 94), ("碰后", 90)),
}

# A single shared bigram such as “关系” or “速度” is not evidence of a
# knowledge point.  Removing these generic fragments prevents false positives
# like “随时间变化关系” -> “功能关系”.
GENERIC_KNOWLEDGE_BIGRAMS = {
    "关系", "定律", "运动", "能量", "质量", "速度", "时间", "变化", "平衡",
    "实验", "测量", "方法", "电路", "图像", "作用", "过程", "状态", "条件",
    "分析", "问题", "规律", "描述", "基本", "现象", "大小", "方向", "物理",
    "牛顿", "顿第", "第一", "一律", "第二", "二定", "第三", "三定",
}


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
                       qti.stem_clean_text, qti.analysis_text, qti.options_json,
                       qti.figures_json
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
            prompt_text = " ".join([
                str(question.get("canonical_title") or ""),
                str(question.get("title_text") or ""),
                _question_prompt_only(question.get("stem_clean_text")),
                _question_prompt_only(question.get("stem_text")),
            ])
            options_text = _question_options_text(
                question.get("options_json"),
                question.get("stem_clean_text"),
                question.get("stem_text"),
            )
            figure_text, figure_count = _question_figure_text(question.get("figures_json"))
            analysis_text = str(question.get("analysis_text") or "")
            primary_corpus = _search_text(prompt_text)
            options_corpus = _search_text(options_text)
            figure_corpus = _search_text(figure_text)
            analysis_corpus = _search_text(analysis_text)
            content_quality = _assess_question_content(
                prompt_text,
                options_text,
                figure_count=figure_count,
                has_figure_text=bool(figure_text.strip()),
            )
            ranked = sorted(
                (
                    (
                        _question_knowledge_score(
                            point,
                            prompt_corpus=primary_corpus,
                            options_corpus=options_corpus,
                            figure_corpus=figure_corpus,
                            analysis_corpus=analysis_corpus,
                        ),
                        point,
                    )
                    for point in points
                ),
                key=lambda item: (-item[0], item[1]["topic3_id"]),
            )
            suggestions = [] if content_quality["status"] != "ok" else [
                {
                    **point,
                    "score": score,
                    "confidence": _confidence(score),
                    "evidence_source": _question_knowledge_source(
                        point,
                        prompt_corpus=primary_corpus,
                        options_corpus=options_corpus,
                        figure_corpus=figure_corpus,
                        analysis_corpus=analysis_corpus,
                    ),
                    "rationale": _question_knowledge_rationale(
                        point,
                        score=score,
                        prompt_corpus=primary_corpus,
                        options_corpus=options_corpus,
                        figure_corpus=figure_corpus,
                        analysis_corpus=analysis_corpus,
                    ),
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
            second_score = int(suggestions[1]["score"]) if len(suggestions) > 1 else 0
            top_topic_name = _search_text(suggestions[0].get("topic3_name")) if suggestions else ""
            top_has_primary_direct_evidence = bool(top_topic_name and top_topic_name in primary_corpus)
            primary_score = score_by_id.get(current_ids[0], 0) if current_ids else 0

            if content_quality["status"] != "ok":
                status = str(content_quality["status"])
            elif not current_ids:
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
            # Do not turn a high keyword score into several speculative
            # bindings.  For the narrow auto-fill case, retain only the best
            # direct match.  Existing bindings are never overwritten here.
            if status == "missing" and top_score >= KNOWLEDGE_AUTO_FIX_THRESHOLD and suggested_ids:
                recommended_ids = [suggested_ids[0]]
            auto_fix_safe = (
                status == "missing"
                and top_score >= KNOWLEDGE_AUTO_FIX_THRESHOLD
                and top_has_primary_direct_evidence
                and top_score - second_score >= 20
                and len(recommended_ids) == 1
                and recommended_ids != current_ids
            )
            item = {
                "question_id": question_id,
                "title_preview": " ".join(str(question.get("title_text") or question.get("canonical_title") or "").split())[:160],
                "status": status,
                "content_quality": content_quality,
                "current": current_with_evidence,
                "suggestions": suggestions,
                "recommended_topic3_ids": recommended_ids,
                "target_count": MAX_KNOWLEDGE_POINTS_PER_QUESTION,
                "auto_fix_safe": auto_fix_safe,
                "auto_fix_evidence": {
                    "top_score": top_score,
                    "second_score": second_score,
                    "score_margin": top_score - second_score,
                    "direct_match_in_title_or_stem": top_has_primary_direct_evidence,
                },
                "reason": (
                    str(content_quality["message"])
                    if status in {"content_fragment", "suspected_cross_subject"}
                    else "题目正文直接命中了新的三级知识点，且当前主知识点缺少文本证据。"
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
                "missing": sum(item["status"] == "missing" for item in items),
                "healthy": sum(item["status"] == "healthy" for item in items),
                "incomplete": sum(item["status"] == "incomplete" for item in items),
                "suspected_mismatch": sum(item["status"] == "suspected_mismatch" for item in items),
                "needs_review": sum(item["status"] == "needs_review" for item in items),
                "content_fragment_count": sum(item["status"] == "content_fragment" for item in items),
                "suspected_cross_subject_count": sum(item["status"] == "suspected_cross_subject" for item in items),
                "option_evidence_count": sum(
                    bool(item["content_quality"].get("has_option_evidence")) for item in items
                ),
                "figure_review_required_count": sum(
                    bool(item["content_quality"].get("requires_image_review")) for item in items
                ),
                "safe_fix_count": len(safe_updates),
                "high_confidence_top_count": sum(
                    bool(item["suggestions"]) and int(item["suggestions"][0]["score"]) >= 80
                    for item in items
                ),
                "review_ready_count": sum(
                    bool(item["suggestions"])
                    and int(item["suggestions"][0]["score"]) >= 80
                    and int(item["auto_fix_evidence"]["score_margin"]) >= 15
                    for item in items
                ),
                "ambiguous_top_count": sum(
                    bool(item["suggestions"])
                    and int(item["auto_fix_evidence"]["score_margin"]) < 10
                    for item in items
                ),
                "no_reliable_suggestion_count": sum(
                    not item["suggestions"] or int(item["suggestions"][0]["score"]) < 45
                    for item in items
                ),
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


def _knowledge_score(
    corpus: str,
    point: dict[str, Any],
    *,
    primary_corpus: str | None = None,
) -> int:
    full_score = _knowledge_score_for_text(corpus, point)
    if primary_corpus is None:
        return full_score
    # An exact match found only in an appended answer or analysis is useful for
    # review, but must rank below strong evidence in the actual question.
    primary_score = _knowledge_score_for_text(primary_corpus, point)
    return max(primary_score, min(full_score, 88))


def _knowledge_score_for_text(corpus: str, point: dict[str, Any]) -> int:
    topic3 = _search_text(point.get("topic3_name"))
    topic2 = _search_text(point.get("topic2_name"))
    topic1 = _search_text(point.get("topic1_name"))
    if topic3 and topic3 in corpus:
        return 100
    cue_score = max(
        (
            score
            for cue, score in KNOWLEDGE_CONCEPT_CUES.get(str(point.get("topic3_name") or ""), ())
            if _search_text(cue) in corpus
        ),
        default=0,
    )
    score = 0
    source_pairs = _distinctive_bigrams(corpus)
    for value, weight in ((topic3, 70), (topic2, 35), (topic1, 15)):
        if not value:
            continue
        if value in corpus:
            score = max(score, weight)
        value_pairs = _distinctive_bigrams(value)
        overlap_count = len(source_pairs & value_pairs)
        # Fuzzy evidence must contain at least two distinctive fragments.
        # Exact two-character terms were already handled by `value in corpus`.
        if value_pairs and overlap_count >= 2:
            overlap = len(source_pairs & value_pairs) / len(value_pairs)
            score = max(score, round(weight * overlap))
        elif value_pairs and overlap_count == 1:
            # Preserve a weak nearest-parent hint for terse queries, but keep it
            # below the suggestion threshold.
            score = max(score, min(round(weight / len(value_pairs)), 12))
    return max(score, cue_score)


def _distinctive_bigrams(value: str) -> set[str]:
    return _bigrams(value) - GENERIC_KNOWLEDGE_BIGRAMS


def _question_knowledge_layers(
    point: dict[str, Any],
    *,
    prompt_corpus: str,
    options_corpus: str,
    figure_corpus: str,
    analysis_corpus: str,
) -> list[tuple[str, str, int]]:
    layers = (
        ("prompt", prompt_corpus, 100),
        ("options", options_corpus, 90),
        ("figure", figure_corpus, 86),
        ("analysis", analysis_corpus, 84),
    )
    return [
        (source, corpus, min(_knowledge_score_for_text(corpus, point), cap) if corpus else 0)
        for source, corpus, cap in layers
    ]


def _question_knowledge_score(
    point: dict[str, Any],
    *,
    prompt_corpus: str,
    options_corpus: str,
    figure_corpus: str,
    analysis_corpus: str,
) -> int:
    return max(
        (
            score
            for _, _, score in _question_knowledge_layers(
                point,
                prompt_corpus=prompt_corpus,
                options_corpus=options_corpus,
                figure_corpus=figure_corpus,
                analysis_corpus=analysis_corpus,
            )
        ),
        default=0,
    )


def _question_knowledge_source(
    point: dict[str, Any],
    *,
    prompt_corpus: str,
    options_corpus: str,
    figure_corpus: str,
    analysis_corpus: str,
) -> str:
    layers = _question_knowledge_layers(
        point,
        prompt_corpus=prompt_corpus,
        options_corpus=options_corpus,
        figure_corpus=figure_corpus,
        analysis_corpus=analysis_corpus,
    )
    best = max(layers, key=lambda item: item[2], default=("none", "", 0))
    return best[0] if best[2] > 0 else "none"


def _question_knowledge_rationale(
    point: dict[str, Any],
    *,
    score: int,
    prompt_corpus: str,
    options_corpus: str,
    figure_corpus: str,
    analysis_corpus: str,
) -> str:
    source = _question_knowledge_source(
        point,
        prompt_corpus=prompt_corpus,
        options_corpus=options_corpus,
        figure_corpus=figure_corpus,
        analysis_corpus=analysis_corpus,
    )
    corpus_by_source = {
        "prompt": prompt_corpus,
        "options": options_corpus,
        "figure": figure_corpus,
        "analysis": analysis_corpus,
    }
    label_by_source = {
        "prompt": "题干",
        "options": "选项",
        "figure": "图片说明",
        "analysis": "解析",
    }
    corpus = corpus_by_source.get(source, "")
    phrase = _knowledge_evidence_phrase(corpus, point)
    topic3 = str(point.get("topic3_name") or "")
    if phrase:
        suffix = "；解析证据已降权。" if source == "analysis" else "。"
        return f"{label_by_source.get(source, '题目')}中的“{phrase}”支持“{topic3}”{suffix}"
    return f"{label_by_source.get(source, '题目')}与“{topic3}”存在多个有效关键词重合，分层匹配分为 {score}。"


def _knowledge_evidence_phrase(corpus: str, point: dict[str, Any]) -> str | None:
    topic3 = str(point.get("topic3_name") or "")
    if _search_text(topic3) in corpus:
        return topic3
    return next(
        (
            cue
            for cue, _ in KNOWLEDGE_CONCEPT_CUES.get(topic3, ())
            if _search_text(cue) in corpus
        ),
        None,
    )


def _decode_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _question_options_text(options_json: Any, *stem_values: Any) -> str:
    parts: list[str] = []
    for option in _decode_json_list(options_json):
        if isinstance(option, dict):
            text = option.get("text") or option.get("content") or option.get("value")
        else:
            text = option
        if text:
            parts.append(str(text))
    if not parts:
        for value in stem_values:
            block = _question_option_block(value)
            if block:
                parts.append(block)
    return " ".join(parts)


def _question_figure_text(figures_json: Any) -> tuple[str, int]:
    figures = [item for item in _decode_json_list(figures_json) if isinstance(item, dict)]
    parts = [
        str(value)
        for figure in figures
        for key in ("caption", "caption_text", "alt", "alt_text", "description", "ocr_text")
        if (value := figure.get(key))
    ]
    return " ".join(parts), len(figures)


def _assess_question_content(
    prompt_text: str,
    options_text: str,
    *,
    figure_count: int,
    has_figure_text: bool,
) -> dict[str, Any]:
    combined = f"{prompt_text} {options_text}".strip()
    without_latex_commands = re.sub(r"\\[A-Za-z]+", "", combined)
    semantic_char_count = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", without_latex_commands))
    has_option_evidence = bool(options_text.strip())
    if semantic_char_count < 8:
        requires_image_review = figure_count > 0 and not has_figure_text
        return {
            "status": "content_fragment",
            "semantic_char_count": semantic_char_count,
            "has_option_evidence": has_option_evidence,
            "has_figure_text_evidence": has_figure_text,
            "requires_image_review": requires_image_review,
            "issues": ["正文有效文字过少", *( ["存在图片但没有可检索的图片说明"] if requires_image_review else [])],
            "message": (
                "题目正文疑似表格或图片切分片段，需要回看原图后修复，暂不推荐知识点。"
                if requires_image_review
                else "题目正文有效信息不足，疑似导入切分片段，暂不推荐知识点。"
            ),
        }

    normalized = _search_text(combined).casefold()
    chemistry_cues = (
        "mol", "反应热", "化学键", "键能", "焓变", "氧化还原", "有机物", "化学反应", "元素周期",
    )
    matched_chemistry = [cue for cue in chemistry_cues if _search_text(cue).casefold() in normalized]
    if len(matched_chemistry) >= 2:
        return {
            "status": "suspected_cross_subject",
            "semantic_char_count": semantic_char_count,
            "has_option_evidence": has_option_evidence,
            "has_figure_text_evidence": has_figure_text,
            "requires_image_review": False,
            "issues": [f"检测到跨学科线索：{'、'.join(matched_chemistry[:4])}"],
            "message": "题目包含多个化学学科线索，疑似混入物理题库，已停止知识点推荐。",
        }
    return {
        "status": "ok",
        "semantic_char_count": semantic_char_count,
        "has_option_evidence": has_option_evidence,
        "has_figure_text_evidence": has_figure_text,
        "requires_image_review": False,
        "issues": [],
        "message": "题目内容可用于知识点诊断。",
    }


def _question_prompt_only(value: Any) -> str:
    """Exclude options and appended answers/analyses from prompt evidence."""
    text = str(value or "")
    answer_positions = [
        position
        for marker in ("【答案】", "【解析】", "答案：", "解析：")
        if (position := text.find(marker)) >= 0
    ]
    before_answer = text[: min(answer_positions)] if answer_positions else text
    option_match = re.search(r"(?:^|\n)\s*(?:>\s*)?[A-HＡ-Ｈ][.．、]\s*", before_answer)
    return before_answer[: option_match.start()] if option_match else before_answer


def _question_option_block(value: Any) -> str:
    text = str(value or "")
    answer_positions = [
        position
        for marker in ("【答案】", "【解析】", "答案：", "解析：")
        if (position := text.find(marker)) >= 0
    ]
    before_answer = text[: min(answer_positions)] if answer_positions else text
    option_match = re.search(r"(?:^|\n)\s*(?:>\s*)?[A-HＡ-Ｈ][.．、]\s*", before_answer)
    return before_answer[option_match.start() :] if option_match else ""


def _confidence(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _knowledge_rationale(
    corpus: str,
    point: dict[str, Any],
    score: int,
    *,
    primary_corpus: str | None = None,
) -> str:
    topic3 = str(point.get("topic3_name") or "")
    topic3_key = _search_text(topic3)
    if primary_corpus is not None and topic3_key in primary_corpus:
        return f"题目文本直接包含“{topic3}”。"
    matched_primary_cue = next(
        (
            cue
            for cue, _ in KNOWLEDGE_CONCEPT_CUES.get(topic3, ())
            if primary_corpus is not None and _search_text(cue) in primary_corpus
        ),
        None,
    )
    if matched_primary_cue:
        return f"题干中的“{matched_primary_cue}”是“{topic3}”的直接语义证据。"
    if topic3_key in corpus:
        return f"题目解析或补充文本直接包含“{topic3}”，已按辅助证据降权。"
    matched_cue = next(
        (
            cue
            for cue, _ in KNOWLEDGE_CONCEPT_CUES.get(topic3, ())
            if _search_text(cue) in corpus
        ),
        None,
    )
    if matched_cue:
        return f"题目中的“{matched_cue}”与“{topic3}”直接相关。"
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
