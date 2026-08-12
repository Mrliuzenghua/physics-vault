from __future__ import annotations

import sqlite3

from physics_vault_api.database import apply_connection_pragmas
from physics_vault_api.services.catalog_health import build_catalog_health_report


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_connection_pragmas(conn, writable=False)
    conn.executescript(
        """
        CREATE TABLE questions (
            question_id TEXT PRIMARY KEY,
            canonical_title TEXT,
            difficulty TEXT,
            question_type TEXT,
            status TEXT,
            content_hash TEXT,
            updated_at TEXT
        );
        CREATE TABLE question_text_index (
            question_id TEXT PRIMARY KEY,
            answer_text TEXT,
            analysis_text TEXT
        );
        CREATE TABLE question_knowledge_points (
            question_id TEXT,
            topic3_id TEXT
        );
        """
    )
    return conn


def test_catalog_health_counts_unique_questions_and_archived_duplicates() -> None:
    conn = _connection()
    conn.executemany(
        "INSERT INTO questions VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("Q-healthy", "完整题", "中等", "选择题", "已审核", "hash-1", "2026-01-01"),
            ("Q-risk", "待修复题", "", "选择题", "已审核", "hash-2", "2026-01-02"),
            ("Q-copy-a", "重复甲", "容易", "填空题", "已审核", "same", "2026-01-03"),
            ("Q-copy-b", "重复乙", "容易", "填空题", "已审核", "same", "2026-01-04"),
            ("Q-archived", "已归档副本", "容易", "填空题", "archived_duplicate", "same", "2026-01-05"),
        ],
    )
    conn.executemany(
        "INSERT INTO question_text_index VALUES (?, ?, ?)",
        [
            ("Q-healthy", "A", "解析"),
            ("Q-risk", "", ""),
            ("Q-copy-a", "1", "解析"),
            ("Q-copy-b", "1", "解析"),
        ],
    )
    conn.executemany(
        "INSERT INTO question_knowledge_points VALUES (?, ?)",
        [("Q-healthy", "K-1"), ("Q-copy-a", "K-2"), ("Q-copy-b", "K-2")],
    )

    report = build_catalog_health_report(conn, sample_limit=1)
    issue_counts = {item["code"]: item["count"] for item in report["issues"]}

    assert report["total_questions"] == 4
    assert report["questions_needing_attention"] == 3
    assert report["healthy_questions"] == 1
    assert report["score"] == 25
    assert report["archived_duplicate_count"] == 1
    assert issue_counts == {
        "missing_text_index": 0,
        "missing_answer": 1,
        "missing_analysis": 1,
        "missing_knowledge": 1,
        "incomplete_metadata": 1,
        "duplicate_content": 2,
    }
    duplicate_issue = next(item for item in report["issues"] if item["code"] == "duplicate_content")
    assert len(duplicate_issue["sample_questions"]) == 1


def test_catalog_health_handles_an_empty_database() -> None:
    conn = sqlite3.connect(":memory:")
    apply_connection_pragmas(conn, writable=False)

    assert build_catalog_health_report(conn)["score"] == 100
