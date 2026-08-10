"""Persistent, incrementally refreshed solution-method features."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path
from .retrieval_method_intent import score_method_candidate


METHOD_INDEX_VERSION = "velocity-compensation-v7-segmented"
_BRANCH_QUERIES = {
    "gravity": "重力配速法",
    "electric": "电场配速法",
}


def ensure_method_feature_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS question_method_features (
            question_id TEXT NOT NULL,
            method_id TEXT NOT NULL,
            branch TEXT NOT NULL,
            level TEXT NOT NULL CHECK(level IN ('explicit', 'structural', 'related')),
            score REAL NOT NULL,
            match_basis TEXT NOT NULL,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            index_version TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (question_id, method_id, branch),
            FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS question_method_index_state (
            question_id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            index_version TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_question_method_features_lookup
        ON question_method_features(method_id, branch, level, score DESC, question_id);
        CREATE TABLE IF NOT EXISTS method_retrieval_feedback (
            feedback_id TEXT PRIMARY KEY,
            question_id TEXT NOT NULL,
            method_id TEXT NOT NULL,
            branch TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('correct', 'incorrect', 'missed')),
            reason TEXT,
            operator TEXT NOT NULL DEFAULT 'teacher',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_method_retrieval_feedback_latest
        ON method_retrieval_feedback(question_id, method_id, branch, created_at DESC, feedback_id DESC);
        """
    )


def refresh_question_method_features(
    question_ids: list[str] | None = None,
    *,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    path = Path(db_path) if db_path else default_db_path()
    clean_ids = list(
        dict.fromkeys(
            str(item or "").strip()
            for item in (question_ids or [])
            if str(item or "").strip()
        )
    )
    if question_ids is not None and not clean_ids:
        return {"question_count": 0, "feature_count": 0}
    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        rows = _load_question_rows(
            conn,
            clean_ids if question_ids is not None else None,
        )
        feedback = _latest_feedback(conn, [str(row["question_id"]) for row in rows])
        feature_count = 0
        for row in rows:
            question_id = str(row["question_id"])
            conn.execute(
                "DELETE FROM question_method_features WHERE question_id = ?",
                (question_id,),
            )
            for branch, query in _BRANCH_QUERIES.items():
                match = score_method_candidate(query, row)
                teacher_feedback = feedback.get((question_id, "velocity_compensation", branch))
                if teacher_feedback and teacher_feedback["verdict"] == "incorrect":
                    continue
                if match is None or match.get("branch") != branch:
                    if not teacher_feedback or teacher_feedback["verdict"] not in {"correct", "missed"}:
                        continue
                    match = {
                        "method_id": "velocity_compensation",
                        "branch": branch,
                        "level": "structural",
                        "score": 0.99,
                        "match_basis": "teacher_feedback",
                        "evidence": [teacher_feedback.get("reason") or "教师确认该题使用此方法"],
                    }
                elif teacher_feedback and teacher_feedback["verdict"] in {"correct", "missed"}:
                    match = {
                        **match,
                        "score": max(float(match["score"]), 0.99),
                        "match_basis": "teacher_feedback",
                        "evidence": [
                            teacher_feedback.get("reason") or "教师确认该题使用此方法",
                            *(match.get("evidence") or []),
                        ][:3],
                    }
                conn.execute(
                    """
                    INSERT INTO question_method_features (
                        question_id, method_id, branch, level, score,
                        match_basis, evidence_json, index_version, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(question_id, method_id, branch) DO UPDATE SET
                        level = excluded.level,
                        score = excluded.score,
                        match_basis = excluded.match_basis,
                        evidence_json = excluded.evidence_json,
                        index_version = excluded.index_version,
                        updated_at = excluded.updated_at
                    """,
                    (
                        question_id,
                        str(match["method_id"]),
                        branch,
                        str(match["level"]),
                        float(match["score"]),
                        str(match["match_basis"]),
                        json.dumps(match.get("evidence") or [], ensure_ascii=False),
                        METHOD_INDEX_VERSION,
                    ),
                )
                feature_count += 1
            conn.execute(
                """
                INSERT INTO question_method_index_state (
                    question_id, content_hash, index_version, updated_at
                ) VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(question_id) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    index_version = excluded.index_version,
                    updated_at = excluded.updated_at
                """,
                (question_id, _content_hash(row), METHOD_INDEX_VERSION),
            )
        conn.commit()
        return {"question_count": len(rows), "feature_count": feature_count}
    finally:
        conn.close()


def ensure_method_feature_index_current(
    *, db_path: str | Path | None = None
) -> dict[str, int]:
    path = Path(db_path) if db_path else default_db_path()
    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        missing = [
            str(row["question_id"])
            for row in conn.execute(
                """
                SELECT q.question_id
                FROM questions q
                LEFT JOIN question_method_index_state s
                  ON s.question_id = q.question_id
                 AND s.index_version = ?
                WHERE s.question_id IS NULL
                ORDER BY q.question_id
                """,
                (METHOD_INDEX_VERSION,),
            ).fetchall()
        ]
    finally:
        conn.close()
    refreshed = refresh_question_method_features(missing, db_path=path) if missing else {
        "question_count": 0,
        "feature_count": 0,
    }
    return {"missing_count": len(missing), **refreshed}


def method_feature_index_health(*, db_path: str | Path | None = None) -> dict[str, int | str]:
    path = Path(db_path) if db_path else default_db_path()
    conn = connect_db(path, writable=True)
    try:
        ensure_method_feature_schema(conn)
        question_count = int(conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0])
        ready_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM question_method_index_state WHERE index_version = ?",
                (METHOD_INDEX_VERSION,),
            ).fetchone()[0]
        )
        feature_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM question_method_features WHERE index_version = ?",
                (METHOD_INDEX_VERSION,),
            ).fetchone()[0]
        )
        return {
            "index_version": METHOD_INDEX_VERSION,
            "question_count": question_count,
            "ready_count": ready_count,
            "missing_count": max(question_count - ready_count, 0),
            "feature_count": feature_count,
        }
    finally:
        conn.close()


def _load_question_rows(
    conn: sqlite3.Connection,
    question_ids: list[str] | None,
) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if question_ids:
        where = f"WHERE q.question_id IN ({','.join('?' for _ in question_ids)})"
        params.extend(question_ids)
    rows = conn.execute(
        f"""
        SELECT q.question_id, q.canonical_title, q.module, q.topic2, q.topic3,
               qti.title_text, qti.stem_text, qti.answer_text,
               qti.analysis_text, qti.tags_json,
               GROUP_CONCAT(DISTINCT kp.topic3_name) AS knowledge_topic3_names
        FROM questions q
        LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
        LEFT JOIN question_knowledge_points qkp ON qkp.question_id = q.question_id
        LEFT JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id
        {where}
        GROUP BY q.question_id
        ORDER BY q.question_id
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _content_hash(row: dict[str, Any]) -> str:
    fields = (
        "canonical_title",
        "title_text",
        "stem_text",
        "answer_text",
        "analysis_text",
        "module",
        "topic2",
        "topic3",
        "tags_json",
        "knowledge_topic3_names",
    )
    payload = "\n".join(str(row.get(field) or "") for field in fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _latest_feedback(
    conn: sqlite3.Connection,
    question_ids: list[str],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not question_ids:
        return {}
    rows = conn.execute(
        f"""
        SELECT * FROM method_retrieval_feedback
        WHERE question_id IN ({','.join('?' for _ in question_ids)})
        ORDER BY created_at DESC, rowid DESC
        """,
        question_ids,
    ).fetchall()
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["question_id"]), str(row["method_id"]), str(row["branch"]))
        latest.setdefault(key, dict(row))
    return latest
