from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from physics_vault_api.app import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(
    "path",
    [
        "/api/audit/batches?limit=0",
        "/api/audit/batches?limit=201",
        "/api/favorites/items?limit=0",
        "/api/favorites/items?limit=201",
        "/api/favorites/items?offset=-1",
        "/api/favorites/items?min_star=6",
        "/api/questions/images/cache?limit=0",
        "/api/questions/images/cache?limit=501",
        "/api/questions/images/available?limit=0",
        "/api/questions/images/available?limit=201",
        "/api/import/batches?limit=0",
        "/api/import/batches?limit=201",
        "/api/import/review-tasks?limit=0",
        "/api/import/review-tasks?limit=201",
        "/api/review-queue?limit=0",
        "/api/review-queue?limit=201",
        "/api/review/drafts/task-1/versions?limit=0",
        "/api/review/drafts/task-1/versions?limit=101",
    ],
)
def test_collection_queries_reject_out_of_range_pagination(path: str, client: TestClient) -> None:
    response = client.get(path)

    assert response.status_code == 422
