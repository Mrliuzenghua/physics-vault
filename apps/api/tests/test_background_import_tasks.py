from fastapi.testclient import TestClient

from physics_vault_api.app import create_app


def test_background_import_uses_sync_fallback_when_queue_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_TASK_QUEUE_ENABLED", "false")
    client = TestClient(create_app())

    uploaded = client.post(
        "/api/import/batches",
        files={"file": ("sample.md", b"1. Sample question\nA. One\nB. Two", "text/markdown")},
    )
    assert uploaded.status_code == 200
    batch_id = uploaded.json()["batch_id"]

    response = client.post(f"/api/import/batches/{batch_id}/recognize-task")
    assert response.status_code == 200
    task = response.json()
    assert task["status"] == "completed"
    assert task["task_type"] == "background_recognize"
    assert task["result"]["batch_id"] == batch_id
    assert task["result"]["task_id"] == task["task_id"]

    overview = client.get("/api/import/batches?limit=20")
    saved_batch = next(item for item in overview.json()["items"] if item["batch_id"] == batch_id)
    assert saved_batch["active_task_id"] == task["task_id"]
    assert saved_batch["active_operation"] == "recognize"

    polled = client.get(f"/api/import/tasks/{task['task_id']}")
    assert polled.status_code == 200
    assert polled.json()["status"] == "completed"


def test_task_queue_status_reports_sync_mode(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_TASK_QUEUE_ENABLED", "false")
    client = TestClient(create_app())

    response = client.get("/api/import/task-queue/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "mode": "synchronous",
        "broker": "none",
        "namespace": "physics-vault",
    }
