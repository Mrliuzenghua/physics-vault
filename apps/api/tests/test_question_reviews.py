from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_reviews import QuestionReviewRepository
from physics_vault_api.repositories.review_queue import ReviewQueueRepository
from physics_vault_api.routers.question_reviews import build_question_reviews_router
from physics_vault_api.services.question_reviews import QuestionReviewService


def test_question_review_actions_use_review_workspace_and_preserve_legacy_paths(tmp_path) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    review_path = tmp_path / "review.sqlite3"
    initialize_database(canonical_path)
    with connect_db(canonical_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type, status) VALUES (?, ?, ?)",
            ("Q-1", "single_choice", "draft"),
        )
        connection.execute(
            "INSERT INTO question_text_index (question_id, stem_text) VALUES (?, ?)",
            ("Q-1", "Original stem"),
        )
        connection.commit()

    queue_repository = ReviewQueueRepository(str(review_path), legacy_db_path=str(canonical_path))
    app = FastAPI()
    app.include_router(
        build_question_reviews_router(
            QuestionReviewService(
                QuestionReviewRepository(str(canonical_path)),
                queue_repository,
            )
        )
    )
    client = TestClient(app)

    review_response = client.post(
        "/questions/Q-1/review",
        json={"action": "approve", "reason": "looks good", "reviewer": "teacher-1"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "\u5df2\u5ba1\u6838"

    fix_response = client.post(
        "/questions/Q-1/propose-fix",
        json={"new_stem_text": "Revised stem", "summary": "clarified"},
    )
    assert fix_response.status_code == 200
    assert fix_response.json()["status"] == "pending"

    issue_response = client.post(
        "/questions/Q-1/report-issue",
        json={"issue_type": "content", "description": "incorrect answer"},
    )
    assert issue_response.status_code == 200
    assert issue_response.json()["status"] == "\u5df2\u9a73\u56de"

    pending_response = client.get("/review-queue/pending-fixes")
    assert pending_response.status_code == 200
    assert pending_response.json()[0]["review_id"] == fix_response.json()["review_id"]
    assert pending_response.json()[0]["summary"] == "clarified"

    rejected_response = client.get("/review-queue/rejected")
    assert rejected_response.status_code == 200
    assert rejected_response.json()[0]["question_id"] == "Q-1"
    assert rejected_response.json()[0]["pending_fix_count"] == 1

    detail_response = client.get(f"/review-queue/{fix_response.json()['review_id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["current_stem_text"] == "Original stem"
    assert detail_response.json()["new_stem_text"] == "Revised stem"

    decide_response = client.post(
        f"/review-queue/{fix_response.json()['review_id']}/decide",
        json={"action": "apply", "reviewer": "teacher-1"},
    )
    assert decide_response.status_code == 200
    assert decide_response.json()["question_status"] == "\u5df2\u5ba1\u6838"

    history_response = client.get("/questions/Q-1/review-history")
    assert history_response.status_code == 200
    assert {item["queue_type"] for item in history_response.json()} == {
        "issue_report",
        "ai_fix",
        "teacher_review",
    }
    assert client.post("/questions/missing/review", json={"action": "approve"}).status_code == 404

    with connect_db(canonical_path, writable=False) as connection:
        row = connection.execute(
            "SELECT status FROM questions WHERE question_id = ?", ("Q-1",)
        ).fetchone()
        stem = connection.execute(
            "SELECT stem_text FROM question_text_index WHERE question_id = ?", ("Q-1",)
        ).fetchone()["stem_text"]
    assert row["status"] == "\u5df2\u5ba1\u6838"
    assert stem == "Revised stem"
