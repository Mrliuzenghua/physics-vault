from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.routers.tasks import build_tasks_router


class TaskServiceStub:
    def __init__(
        self,
        exists=True,
        status="failed",
        task_type="background_pandoc",
        artifact=True,
        audits=True,
    ):
        self.exists, self.status, self.task_type = exists, status, task_type
        self.artifact, self.audits = artifact, audits

    def get_context(self, task_id):
        if not self.exists:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="missing")
        return {
            "artifacts": (
                [{"display_name": "result.docx", "download_url": f"/api/tasks/{task_id}/download", "type": "word_export"}]
                if self.artifact
                else []
            ),
            "audits": (
                [
                    {"audit_id": "new", "action": "retry", "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc), "operator": "a", "confirmed": True},
                    {"audit_id": "old", "action": "submit", "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc), "operator": "b", "confirmed": False},
                ]
                if self.audits
                else []
            ),
            "retry_allowed": self.status == "failed" and self.task_type.startswith("background_"),
            "retry_reason": "Retry is available." if self.status == "failed" and self.task_type.startswith("background_") else "Only failed tasks can be retried.",
        }


def test_context_download_path_empty_values_order_and_retry() -> None:
    service = TaskServiceStub(); app = FastAPI()
    # Router only reads these private collaborators while building health; provide inert placeholders.
    service._import_service = object(); service._dispatcher = type("D", (), {"settings": object()})()
    app.include_router(build_tasks_router(service)); payload = TestClient(app).get("/api/tasks/t-1/context").json()
    assert payload["artifacts"][0]["download_url"] == "/api/tasks/t-1/download"
    assert "\\" not in str(payload["artifacts"]) and "C:" not in str(payload["artifacts"])
    assert [item["audit_id"] for item in payload["audits"]] == ["new", "old"]
    assert payload["retry_allowed"] is True


def test_context_empty_nonretry_and_missing() -> None:
    service = TaskServiceStub(status="completed", task_type="word_export", artifact=False, audits=False); service._import_service = object(); service._dispatcher = type("D", (), {"settings": object()})(); app = FastAPI(); app.include_router(build_tasks_router(service))
    payload = TestClient(app).get("/api/tasks/t/context").json()
    assert payload["artifacts"] == [] and payload["audits"] == [] and payload["retry_allowed"] is False
    unsupported = TaskServiceStub(status="failed", task_type="word_export"); unsupported._import_service = object(); unsupported._dispatcher = type("D", (), {"settings": object()})(); app_unsupported = FastAPI(); app_unsupported.include_router(build_tasks_router(unsupported))
    assert TestClient(app_unsupported).get("/api/tasks/t/context").json()["retry_allowed"] is False
    missing = TaskServiceStub(exists=False); missing._import_service = object(); missing._dispatcher = type("D", (), {"settings": object()})(); app2 = FastAPI(); app2.include_router(build_tasks_router(missing))
    assert TestClient(app2).get("/api/tasks/nope/context").status_code == 404
