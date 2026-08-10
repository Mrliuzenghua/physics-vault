from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_stats import QuestionStatsRepository
from physics_vault_api.routers.question_stats import build_question_stats_router
from physics_vault_api.services.question_stats import QuestionStatsService


def test_question_stats_preserves_legacy_path_and_groups_statuses(tmp_path) -> None:
    db_path = tmp_path / "question-stats.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.executemany(
            "INSERT INTO questions (question_id, question_type, status) VALUES (?, ?, ?)",
            [
                ("Q-1", "single_choice", "approved"),
                ("Q-2", "single_choice", "approved"),
                ("Q-3", "single_choice", "pending"),
            ],
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_question_stats_router(
            QuestionStatsService(QuestionStatsRepository(str(db_path)))
        )
    )

    response = TestClient(app).get("/stats/questions")

    assert response.status_code == 200
    assert response.json() == {"approved": 2, "pending": 1}
