from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.operation_plans import OperationPlanRepository
from physics_vault_api.routers.tag_maintenance import build_tag_maintenance_router
from physics_vault_api.services.operation_plans import OperationPlanService
from physics_vault_api.services.tag_maintenance import TagMaintenanceOperationService


def _client(tmp_path):
    db_path = initialize_database(tmp_path / "tags.sqlite3")
    with connect_db(db_path) as conn:
        for question_id, tags in (("q-tag-1", ["旧标签"]), ("q-tag-2", ["旧标签", "保留"])):
            conn.execute(
                "INSERT INTO questions (question_id, canonical_title, question_type, difficulty) VALUES (?, ?, 'calculation', 3)",
                (question_id, question_id),
            )
            conn.execute(
                "INSERT INTO question_text_index (question_id, tags_json) VALUES (?, ?)",
                (question_id, json.dumps(tags, ensure_ascii=False)),
            )
        conn.commit()
    plans = OperationPlanRepository(tmp_path / "operation-plans.sqlite3")
    service = TagMaintenanceOperationService(
        db_path,
        OperationPlanService(plans),
    )
    app = FastAPI()
    app.include_router(build_tag_maintenance_router(service))
    return TestClient(app), db_path, plans


def _preview_request(question_ids=("q-tag-1", "q-tag-2")):
    return {
        "question_ids": list(question_ids),
        "add_tags": ["新标签"],
        "remove_tags": ["旧标签"],
        "reason": "教师确认统一检索标签",
    }


def test_preview_persists_tag_plan_then_confirm_is_idempotent_and_audited(tmp_path) -> None:
    client, db_path, plans = _client(tmp_path)
    preview = client.post("/api/questions/tags/preview", json=_preview_request())
    assert preview.status_code == 200
    payload = preview.json()
    operation_id = payload["operation_plan"]["operation_id"]
    assert payload["changed_count"] == 2
    assert plans.get(operation_id).status == "planned"
    assert plans.get(operation_id).plan.version_snapshot["tag_maintenance"]["reason"] == "教师确认统一检索标签"

    confirmed = client.post("/api/questions/tags/confirm-operation", json={"operation_id": operation_id})
    replay = client.post("/api/questions/tags/confirm-operation", json={"operation_id": operation_id})
    assert confirmed.json()["status"] == "completed"
    assert replay.json()["idempotent"] is True
    audit_batch_id = confirmed.json()["result"]["audit_batch_id"]
    assert audit_batch_id.startswith("CHG-")
    with connect_db(db_path, writable=False) as conn:
        tags = conn.execute("SELECT tags_json FROM question_text_index ORDER BY question_id").fetchall()
        audit = conn.execute(
            "SELECT change_type, changed_count, reason FROM change_batches WHERE batch_id = ?",
            (audit_batch_id,),
        ).fetchone()
    assert [json.loads(row[0]) for row in tags] == [["新标签"], ["保留", "新标签"]]
    assert tuple(audit) == ("tag_normalization", 2, "教师确认统一检索标签")


def test_tag_plan_conflict_rejects_confirmation_before_any_planned_write(tmp_path) -> None:
    client, db_path, plans = _client(tmp_path)
    operation_id = client.post("/api/questions/tags/preview", json=_preview_request()).json()["operation_plan"]["operation_id"]
    with connect_db(db_path) as conn:
        conn.execute(
            "UPDATE question_text_index SET tags_json = ? WHERE question_id = 'q-tag-1'",
            (json.dumps(["外部变更"], ensure_ascii=False),),
        )
        conn.commit()

    response = client.post("/api/questions/tags/confirm-operation", json={"operation_id": operation_id})
    assert response.status_code == 409
    assert plans.get(operation_id).status == "planned"
    with connect_db(db_path, writable=False) as conn:
        q2_tags = conn.execute("SELECT tags_json FROM question_text_index WHERE question_id = 'q-tag-2'").fetchone()[0]
    assert json.loads(q2_tags) == ["旧标签", "保留"]
