from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3
from time import sleep

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.operation_plans import OperationPlanRepository
from physics_vault_api.repositories.question_write import QuestionWriteRepository
from physics_vault_api.routers.metadata_batch import build_metadata_batch_router
from physics_vault_api.services.metadata_batch import MetadataBatchService
from physics_vault_api.services.operation_plans import OperationPlanService


def _database(tmp_path):
    path = initialize_database(tmp_path / "metadata-operation.sqlite3")
    with sqlite3.connect(path) as conn:
        for question_id in ("q-1", "q-2"):
            conn.execute(
                "INSERT INTO questions (question_id, canonical_title, question_type, difficulty) VALUES (?, ?, 'single_choice', 1)",
                (question_id, question_id),
            )
            conn.execute(
                "INSERT INTO question_text_index (question_id, stem_text, tags_json) VALUES (?, '', '[]')",
                (question_id,),
            )
    return path


def _request(question_ids=("q-1", "q-2")):
    return {
        "question_ids": list(question_ids),
        "fields": ["knowledge_points", "tags", "source"],
        "mode": "manual",
        "manual_values": {
            "knowledge_points": "力学/牛顿定律",
            "tags": ["力学", "批量"],
            "source": "operation-plan-test",
        },
        "force_overwrite": True,
    }


def _client(tmp_path, *, question_repo_type=QuestionWriteRepository, now=None):
    db_path = _database(tmp_path)
    questions = question_repo_type(str(db_path))
    plans = OperationPlanRepository(tmp_path / "operation-plans.sqlite3")
    app = FastAPI()
    app.include_router(
        build_metadata_batch_router(
            MetadataBatchService(questions),
            OperationPlanService(plans, now=now),
        )
    )
    return TestClient(app), questions, plans, db_path


def test_preview_persists_full_payload_and_confirm_replay_writes_each_question_once(tmp_path) -> None:
    client, _, plans, db_path = _client(tmp_path)
    preview = client.post("/api/questions/batch-metadata/preview", json=_request())
    assert preview.status_code == 200
    payload = preview.json()
    operation_id = payload["operation_plan"]["operation_id"]
    execution = payload["operation_plan"]["execution_payload"]
    assert execution["question_ids"] == ["q-1", "q-2"]
    assert {item["question_id"] for item in execution["updates"]} == {"q-1", "q-2"}
    assert set(payload["operation_plan"]["version_snapshot"]["question_versions"]) == {"q-1", "q-2"}
    assert plans.get(operation_id).plan.execution_payload.question_ids == ["q-1", "q-2"]

    confirmed = client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id})
    replay = client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id})
    assert confirmed.json()["status"] == "completed"
    assert confirmed.json()["result"]["updated"] == 2
    assert replay.json()["idempotent"] is True
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT q.module, qti.tags_json, qti.source_text FROM questions q "
            "JOIN question_text_index qti USING(question_id) ORDER BY question_id"
        ).fetchall()
    assert rows == [
        ("力学/牛顿定律", '["力学", "批量"]', "operation-plan-test"),
        ("力学/牛顿定律", '["力学", "批量"]', "operation-plan-test"),
    ]


def test_any_question_version_conflict_returns_409_and_performs_zero_planned_writes(tmp_path) -> None:
    client, questions, plans, db_path = _client(tmp_path)
    operation_id = client.post("/api/questions/batch-metadata/preview", json=_request()).json()["operation_plan"]["operation_id"]
    questions.update_question_metadata("q-1", {"knowledge_point": "external change"})

    response = client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id})
    assert response.status_code == 409
    assert plans.get(operation_id).status == "planned"
    with sqlite3.connect(db_path) as conn:
        q2 = conn.execute("SELECT module FROM questions WHERE question_id='q-2'").fetchone()
        q2_text = conn.execute("SELECT tags_json, source_text FROM question_text_index WHERE question_id='q-2'").fetchone()
    assert q2 == (None,)
    assert q2_text == ("[]", None)


def test_expired_unknown_missing_and_tampered_confirmation_payloads_are_rejected(tmp_path) -> None:
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    client, _, plans, _ = _client(tmp_path, now=lambda: future)
    plan = client.post("/api/questions/batch-metadata/preview", json=_request(("q-1",))).json()["operation_plan"]
    operation_id = plan["operation_id"]

    assert client.post("/api/questions/batch-metadata/confirm-operation", json={}).status_code == 422
    tampered = client.post(
        "/api/questions/batch-metadata/confirm-operation",
        json={"operation_id": operation_id, "question_ids": ["q-2"], "tags": ["tampered"]},
    )
    assert tampered.status_code == 422
    assert plans.get(operation_id).plan.execution_payload.question_ids == ["q-1"]
    assert client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": "OP-unknown"}).status_code == 404
    expired = client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id})
    assert expired.json()["status"] == "expired"


class _CountingQuestionRepository(QuestionWriteRepository):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls = 0

    def update_question_metadata(self, question_id, updates) -> None:
        self.calls += 1
        sleep(0.05)
        super().update_question_metadata(question_id, updates)


def test_concurrent_confirmation_executes_persisted_batch_once(tmp_path) -> None:
    client, questions, _, _ = _client(tmp_path, question_repo_type=_CountingQuestionRepository)
    operation_id = client.post("/api/questions/batch-metadata/preview", json=_request()).json()["operation_plan"]["operation_id"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(
            lambda _: client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id}),
            range(2),
        ))
    assert questions.calls == 2
    assert {response.json()["status"] for response in responses} <= {"executing", "completed"}
    assert client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id}).json()["idempotent"] is True


class _FailingQuestionRepository(QuestionWriteRepository):
    def update_question_metadata(self, question_id, updates) -> None:
        raise RuntimeError("storage write failed")


def test_failed_planned_write_is_not_marked_completed_and_legacy_endpoint_remains_available(tmp_path) -> None:
    client, _, plans, _ = _client(tmp_path, question_repo_type=_FailingQuestionRepository)
    operation_id = client.post("/api/questions/batch-metadata/preview", json=_request(("q-1",))).json()["operation_plan"]["operation_id"]
    failed = client.post("/api/questions/batch-metadata/confirm-operation", json={"operation_id": operation_id})
    assert failed.json()["status"] == "failed"
    assert "failed" in failed.json()["error"]
    assert plans.get(operation_id).status == "failed"

    direct = client.post("/api/questions/batch-metadata", json=_request(("q-1",)))
    assert direct.status_code == 200
    assert direct.json()["failed"] == 1
