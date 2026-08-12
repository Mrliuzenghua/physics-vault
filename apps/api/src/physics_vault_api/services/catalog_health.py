from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogIssueDefinition:
    code: str
    label: str
    description: str
    severity: str
    predicate: str


_ACTIVE_QUESTION = "COALESCE(q.status, '') != 'archived_duplicate'"
_DUPLICATE_CONTENT = """
    TRIM(COALESCE(q.content_hash, '')) != ''
    AND q.content_hash IN (
        SELECT content_hash
        FROM questions
        WHERE COALESCE(status, '') != 'archived_duplicate'
          AND TRIM(COALESCE(content_hash, '')) != ''
        GROUP BY content_hash
        HAVING COUNT(*) > 1
    )
"""

_ISSUES = (
    CatalogIssueDefinition(
        code="missing_text_index",
        label="正文索引缺失",
        description="题目尚未进入正文索引，可能无法被完整检索。",
        severity="danger",
        predicate="qti.question_id IS NULL",
    ),
    CatalogIssueDefinition(
        code="missing_answer",
        label="答案缺失",
        description="正式题目没有可用答案，会影响教师版和自动批改。",
        severity="danger",
        predicate="TRIM(COALESCE(qti.answer_text, '')) = ''",
    ),
    CatalogIssueDefinition(
        code="missing_analysis",
        label="解析缺失",
        description="正式题目没有解析，不利于讲义生成和错题复习。",
        severity="warning",
        predicate="TRIM(COALESCE(qti.analysis_text, '')) = ''",
    ),
    CatalogIssueDefinition(
        code="missing_knowledge",
        label="知识点未绑定",
        description="题目没有结构化知识点，筛选和智能组卷会受影响。",
        severity="warning",
        predicate="NOT EXISTS (SELECT 1 FROM question_knowledge_points qkp WHERE qkp.question_id = q.question_id)",
    ),
    CatalogIssueDefinition(
        code="incomplete_metadata",
        label="基础标签不完整",
        description="题型或难度为空，无法稳定参与题库筛选。",
        severity="warning",
        predicate="TRIM(COALESCE(q.question_type, '')) = '' OR TRIM(COALESCE(q.difficulty, '')) = ''",
    ),
    CatalogIssueDefinition(
        code="duplicate_content",
        label="疑似重复题",
        description="多道正式题具有相同内容指纹，需要人工确认保留版本。",
        severity="warning",
        predicate=_DUPLICATE_CONTENT,
    ),
)


def build_catalog_health_report(conn: sqlite3.Connection, *, sample_limit: int = 4) -> dict[str, Any]:
    """Summarize actionable quality gaps in the canonical question catalog."""
    if not _table_exists(conn, "questions"):
        return _empty_report()

    total_questions = _scalar(conn, f"SELECT COUNT(*) FROM questions q WHERE {_ACTIVE_QUESTION}")
    archived_duplicate_count = _scalar(
        conn,
        "SELECT COUNT(*) FROM questions WHERE COALESCE(status, '') = 'archived_duplicate'",
    )
    has_text_index = _table_exists(conn, "question_text_index")
    has_knowledge_links = _table_exists(conn, "question_knowledge_points")
    join = (
        "LEFT JOIN question_text_index qti ON qti.question_id = q.question_id"
        if has_text_index
        else "LEFT JOIN (SELECT NULL AS question_id, NULL AS answer_text, NULL AS analysis_text) qti ON 1 = 0"
    )

    issues: list[dict[str, Any]] = []
    attention_ids: set[str] = set()
    for definition in _ISSUES:
        predicate = definition.predicate
        if definition.code == "missing_knowledge" and not has_knowledge_links:
            predicate = "1 = 1"
        rows = conn.execute(
            f"""
            SELECT q.question_id, COALESCE(NULLIF(TRIM(q.canonical_title), ''), q.question_id) AS title
            FROM questions q
            {join}
            WHERE {_ACTIVE_QUESTION} AND ({predicate})
            ORDER BY q.updated_at DESC, q.question_id ASC
            """
        ).fetchall()
        question_ids = [str(row["question_id"]) for row in rows]
        attention_ids.update(question_ids)
        issues.append(
            {
                "code": definition.code,
                "label": definition.label,
                "description": definition.description,
                "severity": definition.severity,
                "count": len(rows),
                "sample_questions": [
                    {"question_id": str(row["question_id"]), "title": str(row["title"])}
                    for row in rows[: max(0, sample_limit)]
                ],
            }
        )

    questions_needing_attention = len(attention_ids)
    healthy_questions = max(0, total_questions - questions_needing_attention)
    score = round(healthy_questions * 100 / total_questions) if total_questions else 100
    return {
        "total_questions": total_questions,
        "healthy_questions": healthy_questions,
        "questions_needing_attention": questions_needing_attention,
        "score": score,
        "archived_duplicate_count": archived_duplicate_count,
        "issues": issues,
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _scalar(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def _empty_report() -> dict[str, Any]:
    return {
        "total_questions": 0,
        "healthy_questions": 0,
        "questions_needing_attention": 0,
        "score": 100,
        "archived_duplicate_count": 0,
        "issues": [],
    }
