from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.application import _build_api_compatibility_router
from physics_vault_api.repositories.review_queue import ReviewQueueRepository
from physics_vault_api.routers.review_queue import build_review_queue_router
from physics_vault_api.routers.system_status import build_system_status_router


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
