from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_details import QuestionDetailRepository
from physics_vault_api.routers.question_details import build_question_details_router
from physics_vault_api.services.question_details import QuestionDetailService
from physics_vault_api.repositories.question_write import QuestionWriteRepository
from physics_vault_api.routers.question_updates import build_question_updates_router
from physics_vault_api.services.question_updates import QuestionUpdateService
from physics_vault_api.services.question_write import QuestionWriteService


def test_question_detail_preserves_legacy_path_and_response_aliases(tmp_path) -> None:
    db_path = tmp_path / "question-detail.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO questions (question_id, canonical_title, question_type, difficulty, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Q-1", "Force question", "single_choice", 3, "approved"),
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_question_details_router(
            QuestionDetailService(QuestionDetailRepository(str(db_path)))
        )
    )
    client = TestClient(app)

    response = client.get("/questions/Q-1")

    assert response.status_code == 200
    assert response.json()["question_id"] == "Q-1"
    assert response.json()["type"] == "single_choice"
    assert response.json()["difficulty"] == "3"
    assert response.json()["knowledge_points"] == []
    assert client.get("/questions/missing").status_code == 404


def test_question_assets_preserve_legacy_path_and_ordering(tmp_path) -> None:
    db_path = tmp_path / "question-assets.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type) VALUES (?, ?)",
            ("Q-1", "single_choice"),
        )
        connection.executemany(
            """
            INSERT INTO image_assets (asset_id, filename, file_path, question_id, verified)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("A-2", "two.png", "data/two.png", "Q-1", 0),
                ("A-1", "one.png", "data/one.png", "Q-1", 1),
            ],
        )
        connection.executemany(
            """
            INSERT INTO question_assets (link_id, question_id, asset_id, role, sort_order, is_primary)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("L-2", "Q-1", "A-2", "solution_figure", 2, 0),
                ("L-1", "Q-1", "A-1", "question_figure", 1, 1),
            ],
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_question_details_router(
            QuestionDetailService(QuestionDetailRepository(str(db_path)))
        )
    )

    response = TestClient(app).get("/questions/Q-1/assets")

    assert response.status_code == 200
    assert [asset["asset_id"] for asset in response.json()] == ["A-1", "A-2"]
    assert response.json()[0]["role"] == "question_figure"
    assert response.json()[0]["is_primary"] is True
    assert TestClient(app).get("/questions/missing/assets").json() == []


def test_question_update_merges_partial_payload_and_preserves_figures(tmp_path) -> None:
    db_path = tmp_path / "question-update.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO questions (question_id, canonical_title, question_type, status, difficulty)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Q-1", "Original title", "single_choice", "approved", 2),
        )
        connection.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, options_json, figures_json, answer_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("Q-1", "Original title", "Original title", "[]", '[{"fig_uuid":"A-1"}]', "A"),
        )
        connection.execute(
            "INSERT INTO image_assets (asset_id, filename, file_path) VALUES (?, ?, ?)",
            ("A-1", "figure.png", "data/assets/figure.png"),
        )
        connection.execute(
            "INSERT INTO question_assets (link_id, question_id, asset_id) VALUES (?, ?, ?)",
            ("L-1", "Q-1", "A-1"),
        )
        connection.commit()

    details = QuestionDetailRepository(str(db_path))
    app = FastAPI()
    app.include_router(
        build_question_updates_router(
            QuestionUpdateService(details, QuestionWriteService(QuestionWriteRepository(str(db_path))))
        )
    )

    response = TestClient(app).put("/questions/Q-1", json={"title": "Updated title"})

    assert response.status_code == 200
    assert response.json()["title_text"] == "Updated title"
    assert response.json()["figures"] == [{"fig_uuid": "A-1", "local_path": "data/assets/figure.png"}]
    assert TestClient(app).put("/questions/missing", json={"title": "Missing"}).status_code == 404
