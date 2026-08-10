from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.processing_runs import ProcessingRunRepository
from physics_vault_api.routers.processing_runs import build_processing_runs_router
from physics_vault_api.services.processing_runs import ProcessingRunService


def build_client(db_path: str) -> TestClient:
    app = FastAPI()
    service = ProcessingRunService(ProcessingRunRepository(db_path))
    app.include_router(build_processing_runs_router(service))
    return TestClient(app)


def test_processing_runs_route_preserves_legacy_path_and_filters(tmp_path) -> None:
    db_path = tmp_path / "processing-runs.sqlite3"
    initialize_database(db_path)
    repository = ProcessingRunRepository(str(db_path))

    from physics_vault_api.database import connect_db

    with connect_db(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO processing_runs (
                run_id, pipeline_name, pipeline_version, status, started_at, operator, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("RUN-1", "question_embeddings", "v1", "completed", "2026-08-01T10:00:00Z", "test", "{}"),
                ("RUN-2", "question_embeddings", "v1", "running", "2026-08-02T10:00:00Z", "test", "{}"),
                ("RUN-3", "other_pipeline", "v1", "running", "2026-08-03T10:00:00Z", "test", "{}"),
            ],
        )
        connection.commit()

    response = build_client(str(db_path)).get(
        "/processing-runs",
        params={"pipeline_name": "question_embeddings", "status": "running", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "run_id": "RUN-2",
            "pipeline_name": "question_embeddings",
            "pipeline_version": "v1",
            "paper_id": None,
            "question_id": None,
            "status": "running",
            "started_at": "2026-08-02T10:00:00Z",
            "finished_at": None,
            "operator": "test",
            "summary_json": "{}",
        }
    ]
