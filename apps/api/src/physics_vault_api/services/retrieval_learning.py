"""Long-running learning signals for retrieval quality."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path
from .method_feature_index import ensure_method_feature_index_current, ensure_method_feature_schema


METHOD_KNOWLEDGE: dict[str, tuple[str, ...]] = {
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

METHOD_BRANCH_QUERY: dict[tuple[str, str], str] = {
    ("velocity_compensation", "gravity"): "重力配速法",
    ("velocity_compensation", "electric"): "电场配速法",
}

METHOD_BRANCH_TAGS: dict[str, str] = {
    "gravity": "重力配速法",
    "electric": "电场配速法",
}


def load_method_feedback_constraints(
    *,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return latest teacher feedback grouped as retrieval benchmark constraints."""

    path = Path(db_path) if db_path else default_db_path()
    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        rows = conn.execute(
            """
            SELECT * FROM method_retrieval_feedback
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
    finally:
        conn.close()

    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        key = (str(item["question_id"]), str(item["method_id"]), str(item["branch"]))
        latest.setdefault(key, item)

    grouped: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(
        lambda: {"positive_question_ids": [], "negative_question_ids": []}
    )
    for (question_id, method_id, branch), item in latest.items():
        bucket = grouped[(method_id, branch)]
        if item["verdict"] in {"correct", "missed"}:
            bucket["positive_question_ids"].append(question_id)
        elif item["verdict"] == "incorrect":
            bucket["negative_question_ids"].append(question_id)

    constraints: list[dict[str, Any]] = []
    for (method_id, branch), bucket in sorted(grouped.items()):
        query = METHOD_BRANCH_QUERY.get((method_id, branch))
        if not query:
            continue
        constraints.append(
            {
                "case_id": f"teacher_feedback_{method_id}_{branch}",
                "method_id": method_id,
                "branch": branch,
                "query": query,
                "positive_question_ids": sorted(set(bucket["positive_question_ids"])),
                "negative_question_ids": sorted(set(bucket["negative_question_ids"])),
            }
        )
    return constraints


def build_method_retrieval_learning_report(
    *,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize feedback-driven benchmark constraints and metadata upkeep work."""

    path = Path(db_path) if db_path else default_db_path()
    bounded_limit = min(max(int(limit or 50), 1), 200)
    index_refresh = ensure_method_feature_index_current(db_path=path)
    constraints = load_method_feedback_constraints(db_path=path)

    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        feedback_rows = conn.execute(
            """
            SELECT verdict, branch, COUNT(*) AS count
            FROM method_retrieval_feedback
            GROUP BY verdict, branch
            ORDER BY branch, verdict
            """
        ).fetchall()
        recent_feedback = conn.execute(
            """
            SELECT feedback_id, question_id, method_id, branch, verdict,
                   reason, operator, created_at
            FROM method_retrieval_feedback
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (min(bounded_limit, 20),),
        ).fetchall()
        candidate_rows = conn.execute(
            """
            SELECT mf.question_id, mf.method_id, mf.branch, mf.level, mf.score,
                   mf.match_basis, mf.evidence_json,
                   q.canonical_title, q.question_type, q.difficulty, q.source,
                   qti.title_text, qti.tags_json,
                   GROUP_CONCAT(DISTINCT qkp.topic3_id) AS topic3_ids
            FROM question_method_features mf
            JOIN questions q ON q.question_id = mf.question_id
            LEFT JOIN question_text_index qti ON qti.question_id = mf.question_id
            LEFT JOIN question_knowledge_points qkp ON qkp.question_id = mf.question_id
            WHERE mf.level IN ('explicit', 'structural')
              AND mf.method_id = 'velocity_compensation'
              AND mf.score >= 0.88
            GROUP BY mf.question_id, mf.branch
            ORDER BY
              CASE mf.match_basis WHEN 'teacher_feedback' THEN 0 WHEN 'explicit_term' THEN 1 ELSE 2 END,
              mf.score DESC,
              mf.question_id
            """
        ).fetchall()
    finally:
        conn.close()

    candidates: list[dict[str, Any]] = []
    for row in candidate_rows:
        item = dict(row)
        branch = str(item["branch"])
        tags = _loads_list(item.get("tags_json"))
        existing_topics = [
            value.strip()
            for value in str(item.get("topic3_ids") or "").split(",")
            if value.strip()
        ]
        expected_topics = list(METHOD_KNOWLEDGE.get(branch, ()))
        missing_topics = [topic_id for topic_id in expected_topics if topic_id not in existing_topics]
        expected_tags = ["配速法", METHOD_BRANCH_TAGS.get(branch, "")]
        missing_tags = [tag for tag in expected_tags if tag and tag not in tags]
        if not missing_topics and not missing_tags:
            continue
        recommended_topics = list(dict.fromkeys([*expected_topics, *existing_topics]))[:3]
        try:
            evidence = json.loads(str(item.get("evidence_json") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = []
        candidates.append(
            {
                "question_id": str(item["question_id"]),
                "title": " ".join(
                    str(item.get("title_text") or item.get("canonical_title") or "").split()
                )[:120],
                "source": item.get("source"),
                "branch": branch,
                "method_level": item.get("level"),
                "method_score": round(float(item.get("score") or 0), 4),
                "match_basis": item.get("match_basis"),
                "missing_tags": missing_tags,
                "missing_topic3_ids": missing_topics,
                "recommended_topic3_ids": recommended_topics,
                "current_topic3_ids": existing_topics,
                "severity": "high" if item.get("match_basis") == "teacher_feedback" else "medium",
                "evidence_preview": [str(value)[:160] for value in evidence[:2]],
            }
        )
        if len(candidates) >= bounded_limit:
            break

    feedback_summary = {
        f"{row['branch']}:{row['verdict']}": int(row["count"])
        for row in feedback_rows
    }
    positive_count = sum(len(item["positive_question_ids"]) for item in constraints)
    negative_count = sum(len(item["negative_question_ids"]) for item in constraints)
    return {
        "ok": True,
        "learning_loop": {
            "teacher_feedback_is_benchmark": True,
            "positive_feedback_cases": positive_count,
            "negative_feedback_cases": negative_count,
            "metadata_candidate_count": len(candidates),
            "index_refreshed_question_count": int(index_refresh.get("question_count", 0)),
        },
        "feedback_summary": feedback_summary,
        "feedback_benchmark_constraints": constraints,
        "metadata_maintenance_candidates": candidates,
        "recent_feedback": [dict(row) for row in recent_feedback],
        "next_actions": [
            "Run the method benchmark after new teacher feedback.",
            "Confirm or reject high-severity metadata candidates through feedback.",
            "Use metadata candidates to keep method tags and up to three level-3 knowledge points current.",
        ],
        "database_scope": "canonical_read_only_with_learning_report",
    }


def _loads_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]
