from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.repositories.operation_plans import OperationPlanRepository
from physics_vault_api.routers.assets_manager import build_assets_manager_router
from physics_vault_api.schemas.assets_manager import CacheCleanupPreviewResponse, CleanupPreviewResponse, CleanupResponse
from physics_vault_api.services.operation_plans import OperationPlanService


class AssetsStub:
    def __init__(self) -> None:
        self.count = 1
        self.calls: list[str] = []

    def get_cleanup_preview(self): return CleanupPreviewResponse(candidate_count=self.count, reclaimable_bytes=10, protected_count=0, scope="question_bank")
    def get_import_cache_cleanup_preview(self, batch_id=""): return CacheCleanupPreviewResponse(batch_id=batch_id or "batch-1", candidate_count=self.count, reclaimable_bytes=10)
    def get_unused_cache_cleanup_preview(self, batch_id=""): return CacheCleanupPreviewResponse(batch_id=batch_id or "batch-1", candidate_count=self.count, reclaimable_bytes=10)
    def cleanup_unreferenced(self): self.calls.append("unreferenced"); return CleanupResponse(deleted_count=1)
    def cleanup_import_cache(self, batch_id=""): self.calls.append("import:" + batch_id); return CleanupResponse(deleted_count=1)
    def cleanup_unused_cache(self, batch_id=""): self.calls.append("unused:" + batch_id); return CleanupResponse(deleted_count=1)


@pytest.mark.parametrize("path", ["/cleanup-preview", "/cache-cleanup-preview", "/unused-cache-preview"])
def test_previews_persist_operation_plan(tmp_path, path: str) -> None:
    repo = OperationPlanRepository(tmp_path / "plans.sqlite3")
    app = FastAPI(); app.include_router(build_assets_manager_router(AssetsStub(), OperationPlanService(repo)))
    payload = TestClient(app).get("/api/assets" + path).json()
    assert payload["operation_plan"]["operation_id"]
    assert repo.get(payload["operation_plan"]["operation_id"]).status == "planned"


def test_confirm_replay_conflict_and_unknown(tmp_path) -> None:
    repo = OperationPlanRepository(tmp_path / "plans.sqlite3"); assets = AssetsStub()
    app = FastAPI(); app.include_router(build_assets_manager_router(assets, OperationPlanService(repo))); client = TestClient(app)
    plan = client.get("/api/assets/cleanup-preview").json()["operation_plan"]
    assert client.post("/api/assets/confirm-operation", json={}).status_code == 422
    assert client.post("/api/assets/confirm-operation", json={"operation_id": plan["operation_id"]}).json()["status"] == "completed"
    assert client.post("/api/assets/confirm-operation", json={"operation_id": plan["operation_id"]}).json()["idempotent"] is True
    assert assets.calls == ["unreferenced"]
    changed = client.get("/api/assets/unused-cache-preview").json()["operation_plan"]; assets.count = 2
    assert client.post("/api/assets/confirm-operation", json={"operation_id": changed["operation_id"]}).status_code == 409
    assert client.post("/api/assets/confirm-operation", json={"operation_id": "OP-missing"}).status_code == 404
