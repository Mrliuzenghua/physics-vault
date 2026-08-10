from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_write import QuestionWriteRepository
from physics_vault_api.routers.question_versions import build_question_versions_router
from physics_vault_api.services.question_versions import QuestionVersionService
from physics_vault_api.services.question_write import QuestionWriteService


def test_question_version_routes_list_get_and_rollback_with_audit_actor(tmp_path) -> None:
    db_path = tmp_path / "question-versions.sqlite3"
    initialize_database(db_path)
    snapshot = {
        "question_type": "single_choice",
        "title": "Previous title",
        "stem_text": "Previous title",
        "options_json": '[{"opt": "A", "content": "One"}]',
        "sub_questions_json": "[]",
        "tags_json": '["mechanics"]',
        "answer": "A",
        "analysis": "Previous analysis",
        "difficulty": 2,
        "knowledge_point": "Mechanics",
        "source": "paper-2025",
    }
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO questions (question_id, canonical_title, question_type, status)
            VALUES (?, ?, ?, ?)
            """,
            ("Q-1", "Current title", "single_choice", "approved"),
        )
        connection.execute(
            """
            INSERT INTO question_versions (
                version_id, question_id, version_number, snapshot_json, change_summary, modified_by, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("V-1", "Q-1", 1, json.dumps(snapshot), "Initial edit", "author-1", "manual"),
        )
        connection.commit()

    repository = QuestionWriteRepository(str(db_path))
    service = QuestionVersionService(repository, QuestionWriteService(repository))
    app = FastAPI()
    app.include_router(build_question_versions_router(service))
    client = TestClient(app)

    list_response = client.get("/questions/Q-1/versions")
    assert list_response.status_code == 200
    assert list_response.json()[0]["version_id"] == "V-1"
    assert "snapshot" not in list_response.json()[0]

    detail_response = client.get("/questions/Q-1/versions/V-1")
    assert detail_response.status_code == 200
    assert detail_response.json()["snapshot"]["title"] == "Previous title"
    assert client.get("/questions/Q-other/versions/V-1").status_code == 404

    rollback_response = client.post(
        "/questions/Q-1/versions/V-1/rollback",
        json={"modified_by": "teacher-1"},
    )
    assert rollback_response.status_code == 200
    assert rollback_response.json()["restored_version_number"] == 1

    with connect_db(db_path, writable=False) as connection:
        question = connection.execute(
            "SELECT canonical_title FROM questions WHERE question_id = ?", ("Q-1",)
        ).fetchone()
        audit_version = connection.execute(
            """
            SELECT modified_by, source, change_summary
            FROM question_versions
            WHERE question_id = ? AND version_number = 2
            """,
            ("Q-1",),
        ).fetchone()

    assert question["canonical_title"] == "Previous title"
    assert dict(audit_version) == {
        "modified_by": "teacher-1",
        "source": "rollback",
        "change_summary": "Restored from version 1",
    }
