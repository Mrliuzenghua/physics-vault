from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from packages.mcp_contracts.src.runtime import (
    DatabaseRuntime,
    MCPServiceFactory,
    build_task_action_context,
    clean_args,
    tool_error,
)


def test_database_runtime_preserves_formal_read_only_and_review_initialization(tmp_path: Path) -> None:
    formal_path = tmp_path / "canonical.sqlite3"
    review_path = tmp_path / "review" / "review.sqlite3"
    with sqlite3.connect(formal_path) as conn:
        conn.execute("CREATE TABLE questions (question_id TEXT PRIMARY KEY)")

    initialized: list[sqlite3.Connection] = []

    def ensure_review_schema(conn: sqlite3.Connection) -> None:
        initialized.append(conn)
        conn.execute("CREATE TABLE review_tasks (task_id TEXT PRIMARY KEY)")
        conn.commit()

    runtime = DatabaseRuntime(
        formal_db_path=lambda: formal_path,
        review_db_path=lambda: review_path,
        ensure_review_schema=ensure_review_schema,
    )

    with runtime.connect_formal_read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO questions(question_id) VALUES ('q-001')")

    with runtime.connect_review() as conn:
        conn.execute("INSERT INTO review_tasks(task_id) VALUES ('review-001')")
        assert conn.execute("SELECT task_id FROM review_tasks").fetchone()[0] == "review-001"

    assert review_path.exists()
    assert initialized


def test_runtime_payloads_and_audit_context_keep_mcp_compatibility() -> None:
    assert clean_args({"missing": None, "empty": "", "zero": 0, "false": False}) == {
        "zero": 0,
        "false": False,
    }
    assert tool_error("INVALID_ARGUMENT", "bad input", field="query", retryable=True) == {
        "ok": False,
        "error": "bad input",
        "error_info": {
            "code": "INVALID_ARGUMENT",
            "message": "bad input",
            "retryable": True,
            "details": {"field": "query"},
        },
    }

    context = build_task_action_context(" source ", " session ", " operator ", confirmed=True)
    assert (context.source, context.session_id, context.operator, context.confirmed) == (
        "source",
        "session",
        "operator",
        True,
    )


def test_service_factory_is_lazy_and_uses_configured_database_paths(tmp_path: Path) -> None:
    factory = MCPServiceFactory(
        formal_db_path=lambda: tmp_path / "canonical.sqlite3",
        review_db_path=lambda: tmp_path / "review.sqlite3",
    )

    # Construction must not import application services, which is what keeps
    # this shared contracts layer free of an import-time dependency cycle.
    assert factory.formal_db_path().name == "canonical.sqlite3"
    assert factory.review_db_path().name == "review.sqlite3"
