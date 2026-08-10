from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_imports import QuestionImportRepository
from physics_vault_api.repositories.review_queue import ReviewQueueRepository
from physics_vault_api.routers.question_imports import build_question_imports_router
from physics_vault_api.services.question_imports import QuestionImportService


def test_question_import_preserves_legacy_path_and_creates_review_audit(tmp_path) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    review_path = tmp_path / "review.sqlite3"
    initialize_database(canonical_path)
    with connect_db(canonical_path) as connection:
        connection.execute(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("KP-1", "Force", "T2", "Mechanics", "T1", "Physics"),
        )
        connection.execute(
            "INSERT INTO image_assets (asset_id, filename, file_path) VALUES (?, ?, ?)",
            ("A-1", "diagram.png", "data/diagram.png"),
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_question_imports_router(
            QuestionImportService(
                QuestionImportRepository(str(canonical_path)),
                ReviewQueueRepository(str(review_path), legacy_db_path=str(canonical_path)),
            )
        )
    )
    response = TestClient(app).post(
        "/questions/import",
        json={
            "classification": {"question_type": "single_choice", "difficulty": 2},
            "source": {"question_no": 3},
            "content": {"stem": "Choose one", "answer": "A"},
            "knowledge_points": [{"topic3_id": "KP-1", "rank": 1}, {"topic3_id": "missing", "rank": 2}],
            "images": [{"asset_id": "A-1", "filename": "diagram.png"}],
            "reviewer": "teacher-1",
            "note": "approved import",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question_id"] == "Q00000001"
    assert body["status"] == "\u5df2\u5ba1\u6838"
    assert body["knowledge_points_inserted"] == 1
    assert body["images_linked"] == 1
    assert body["skipped_knowledge_points"] == ["missing"]

    with connect_db(canonical_path, writable=False) as connection:
        assert connection.execute("SELECT COUNT(*) FROM question_knowledge_points").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM question_assets").fetchone()[0] == 1
    with connect_db(review_path, writable=False) as connection:
        audit = connection.execute(
            "SELECT queue_type, status FROM review_queue WHERE review_id = ?", (body["review_id"],)
        ).fetchone()
    assert tuple(audit) == ("import_approve", "approved")

    assert TestClient(app).post("/questions/import", json={"content": {}}).status_code == 400
