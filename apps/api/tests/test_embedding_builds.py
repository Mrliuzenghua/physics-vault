from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.routers.embedding_builds import build_embedding_builds_router
from physics_vault_api.services.embedding_builds import EmbeddingBuildService


def test_embedding_build_dry_run_preserves_legacy_path_and_records_run(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "embeddings.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type, status) VALUES (?, ?, ?)",
            ("Q-1", "single_choice", "approved"),
        )
        connection.execute(
            "INSERT INTO question_text_index (question_id, stem_text) VALUES (?, ?)",
            ("Q-1", "A physics question"),
        )
        connection.commit()

    monkeypatch.setattr("physics_vault_api.services.embedding_builds.default_db_path", lambda: db_path)
    app = FastAPI()
    app.include_router(build_embedding_builds_router(EmbeddingBuildService()))
    response = TestClient(app).post("/embeddings/questions/build", json={"dry_run": True, "limit": 1})

    assert response.status_code == 200
    assert response.json()["processed_count"] == 1
    assert response.json()["embedded_count"] == 0
    with connect_db(db_path, writable=False) as connection:
        assert connection.execute("SELECT status FROM processing_runs").fetchone()["status"] == "completed"
