from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.application import _build_api_compatibility_router
from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.embedding_status import EmbeddingStatusRepository
from physics_vault_api.routers.embedding_status import build_embedding_status_router
from physics_vault_api.services.embedding_status import EmbeddingStatusService


def test_embedding_status_serves_canonical_and_legacy_compatibility_paths(tmp_path) -> None:
    db_path = tmp_path / "embedding-status.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO embeddings (
                embedding_id, owner_type, owner_id, vector_type, model_name, model_version,
                dimensions, vector_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("E-1", "question", "Q-1", "content", "model-a", "v1", 3, "[0,0,1]", "2026-08-01"),
                ("E-2", "question", "Q-2", "content", "model-a", "v1", 3, "[0,1,0]", "2026-08-02"),
                ("E-3", "paper", "P-1", "content", "model-b", "v1", 3, "[1,0,0]", "2026-08-03"),
            ],
        )
        connection.commit()

    router = build_embedding_status_router(
        EmbeddingStatusService(EmbeddingStatusRepository(str(db_path)))
    )
    app = FastAPI()
    app.include_router(router)
    app.include_router(_build_api_compatibility_router(router))

    client = TestClient(app)
    response = client.get("/api/embeddings/status")

    assert response.status_code == 200
    assert response.json() == [
        {
            "model_name": "model-a",
            "model_version": "v1",
            "vector_type": "content",
            "owner_count": 2,
            "last_updated_at": "2026-08-02",
        }
    ]
    assert client.get("/embeddings/status").json() == response.json()
