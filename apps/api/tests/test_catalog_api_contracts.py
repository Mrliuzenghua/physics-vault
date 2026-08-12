from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import sqlite3

from physics_vault_api.application import _build_api_compatibility_router
from physics_vault_api.repositories.review_queue import ReviewQueueRepository
from physics_vault_api.routers.review_queue import build_review_queue_router
from physics_vault_api.routers.system_status import build_system_status_router
import physics_vault_api.routers.system_status as system_status_module


def test_review_queue_serves_canonical_and_legacy_compatibility_paths(tmp_path) -> None:
    repository = ReviewQueueRepository(str(tmp_path / "review.sqlite3"))
    repository.create(
        question_id="Q-1",
        queue_type="quality",
        status="pending",
        reason="Needs a teacher check",
    )
    router = build_review_queue_router(repository)
    app = FastAPI()
    app.include_router(router)
    app.include_router(_build_api_compatibility_router(router))
    client = TestClient(app)

    canonical = client.get("/api/review-queue", params={"status": "pending"})

    assert canonical.status_code == 200
    assert canonical.json()[0]["entity_id"] == "Q-1"
    assert client.get("/review-queue", params={"status": "pending"}).json() == canonical.json()


def test_system_health_has_a_named_canonical_contract() -> None:
    app = FastAPI()
    app.include_router(build_system_status_router(object()))

    response = TestClient(app).get("/api/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert app.openapi()["paths"]["/api/system/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/HealthResponse")


def test_missing_knowledge_review_excludes_archived_and_returns_diagnosis(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE questions (question_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT);
            CREATE TABLE question_knowledge_points (question_id TEXT, topic3_id TEXT);
            INSERT INTO questions VALUES ('Q-missing', '已审核', '2026-08-12');
            INSERT INTO questions VALUES ('Q-bound', '已审核', '2026-08-11');
            INSERT INTO questions VALUES ('Q-archived', 'archived_duplicate', '2026-08-10');
            INSERT INTO question_knowledge_points VALUES ('Q-bound', 'K-1');
            """
        )

    class FakeMetadataService:
        def diagnose_question_knowledge_points(self, question_ids):
            assert question_ids == ["Q-missing"]
            return {
                "items": [{"question_id": "Q-missing", "suggestions": [], "auto_fix_safe": False}],
                "summary": {"missing": 1, "safe_fix_count": 0},
            }

    monkeypatch.setattr(system_status_module, "default_db_path", lambda: db_path)
    app = FastAPI()
    app.include_router(build_system_status_router(object(), FakeMetadataService()))

    payload = TestClient(app).get("/api/system/catalog-health/missing-knowledge").json()

    assert payload["total"] == 1
    assert payload["items"][0]["question_id"] == "Q-missing"
