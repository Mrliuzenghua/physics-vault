from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from time import sleep

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.repositories.operation_plans import OperationPlanRepository
from physics_vault_api.repositories.review_drafts import SQLiteReviewDraftRepository
from physics_vault_api.routers.review_save import build_review_save_router
from physics_vault_api.services.operation_plans import OperationPlanService


def _state(title: str) -> dict[str, object]:
    return {
        "drafts": [{"question_id": "draft-1", "title": title}],
        "knowledge_drafts": [],
        "task_meta": {},
        "current_index": 0,
        "queue": "risk",
    }


def _client(tmp_path, *, now=None, repository_type=SQLiteReviewDraftRepository):
    drafts = repository_type(str(tmp_path / "review-drafts.sqlite3"))
    plans = OperationPlanRepository(tmp_path / "operation-plans.sqlite3")
    app = FastAPI()
    app.include_router(
        build_review_save_router(
            draft_repository=drafts,
            operation_plan_service=OperationPlanService(plans, now=now),
        )
    )
    return TestClient(app), drafts, plans


def test_delete_preview_persists_and_confirm_replay_is_once(tmp_path) -> None:
    client, drafts, plans = _client(tmp_path)
    first = drafts.save("task-delete", 0, _state("first"))

    preview = client.post("/api/review/drafts/task-delete/delete-preview")
    assert preview.status_code == 200
    payload = preview.json()
    operation_id = payload["operation_plan"]["operation_id"]
    assert payload["action"] == "review_drafts.delete"
    assert payload["task_id"] == "task-delete"
    assert payload["draft_version"] == first.version
    assert payload["reversible"] is False
    assert payload["expires_at"]
    assert plans.get(operation_id).status == "planned"
    assert client.post("/api/review/drafts/confirm-operation", json={}).status_code == 422

    confirmed = client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id})
    replay = client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id})
    assert confirmed.json()["status"] == "completed"
    assert replay.json()["idempotent"] is True
    assert replay.json()["result"] == confirmed.json()["result"]
    assert drafts.get("task-delete") is None


def test_restore_preview_persists_target_and_replay_does_not_create_another_version(tmp_path) -> None:
    client, drafts, plans = _client(tmp_path)
    first = drafts.save("task-restore", 0, _state("first"))
    second = drafts.save("task-restore", first.version, _state("second"))

    preview = client.post("/api/review/drafts/task-restore/restore-preview", json={"version": first.version})
    assert preview.status_code == 200
    payload = preview.json()
    operation_id = payload["operation_plan"]["operation_id"]
    targets = {item["type"]: item["id"] for item in payload["operation_plan"]["targets"]}
    assert payload["action"] == "review_drafts.restore"
    assert payload["draft_version"] == second.version
    assert payload["reversible"] is True
    assert targets == {
        "review_draft": "task-restore",
        "review_draft_base_version": str(second.version),
        "review_draft_restore_version": str(first.version),
    }
    assert plans.get(operation_id).status == "planned"

    confirmed = client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id})
    replay = client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id})
    assert confirmed.json()["result"]["version"] == 3
    assert confirmed.json()["result"]["state"]["drafts"][0]["title"] == "first"
    assert replay.json()["idempotent"] is True
    assert [item.version for item in drafts.list_versions("task-restore")] == [3, 2, 1]


def test_previewed_draft_version_conflict_and_unknown_operation_are_http_errors(tmp_path) -> None:
    client, drafts, plans = _client(tmp_path)
    first = drafts.save("task-conflict", 0, _state("first"))
    operation_id = client.post("/api/review/drafts/task-conflict/delete-preview").json()["operation_plan"]["operation_id"]
    drafts.save("task-conflict", first.version, _state("changed"))

    conflict = client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id})
    assert conflict.status_code == 409
    assert plans.get(operation_id).status == "planned"

    restore_first = drafts.save("task-restore-conflict", 0, _state("first"))
    restore_second = drafts.save("task-restore-conflict", restore_first.version, _state("second"))
    restore_operation = client.post(
        "/api/review/drafts/task-restore-conflict/restore-preview",
        json={"version": restore_first.version},
    ).json()["operation_plan"]["operation_id"]
    drafts.save("task-restore-conflict", restore_second.version, _state("changed"))
    assert client.post(
        "/api/review/drafts/confirm-operation",
        json={"operation_id": restore_operation},
    ).status_code == 409
    assert client.post("/api/review/drafts/confirm-operation", json={"operation_id": "OP-unknown"}).status_code == 404


def test_expired_delete_plan_is_not_executed(tmp_path) -> None:
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    client, drafts, plans = _client(tmp_path, now=lambda: future)
    drafts.save("task-expired", 0, _state("first"))
    operation_id = client.post("/api/review/drafts/task-expired/delete-preview").json()["operation_plan"]["operation_id"]

    expired = client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id})
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert plans.get(operation_id).status == "expired"
    assert drafts.get("task-expired") is not None


def test_legacy_direct_delete_and_restore_routes_remain_available(tmp_path) -> None:
    client, drafts, _ = _client(tmp_path)
    drafts.save("task-legacy-delete", 0, _state("first"))
    direct_delete = client.delete("/api/review/drafts/task-legacy-delete")
    assert direct_delete.status_code == 200
    assert direct_delete.json() == {"task_id": "task-legacy-delete", "deleted": True}

    first = drafts.save("task-legacy-restore", 0, _state("first"))
    second = drafts.save("task-legacy-restore", first.version, _state("second"))
    direct_restore = client.post(
        "/api/review/drafts/task-legacy-restore/restore",
        json={"version": first.version, "base_version": second.version},
    )
    assert direct_restore.status_code == 200
    assert direct_restore.json()["version"] == 3


class _CountingDraftRepository(SQLiteReviewDraftRepository):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.delete_calls = 0

    def delete(self, task_id: str) -> None:
        self.delete_calls += 1
        sleep(0.05)
        super().delete(task_id)


def test_concurrent_confirmation_claims_delete_plan_once(tmp_path) -> None:
    client, drafts, _ = _client(tmp_path, repository_type=_CountingDraftRepository)
    drafts.save("task-concurrent", 0, _state("first"))
    operation_id = client.post("/api/review/drafts/task-concurrent/delete-preview").json()["operation_plan"]["operation_id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id}), range(2)))

    assert drafts.delete_calls == 1
    assert sorted(response.json()["status"] for response in responses) == ["completed", "executing"]
    assert client.post("/api/review/drafts/confirm-operation", json={"operation_id": operation_id}).json()["idempotent"] is True
