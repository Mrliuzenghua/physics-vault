from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.knowledge_points import KnowledgePointRepository
from physics_vault_api.repositories.operation_plans import OperationPlanRepository
from physics_vault_api.routers.knowledge_points import build_knowledge_points_router
from physics_vault_api.services.knowledge_points import KnowledgePointService
from physics_vault_api.services.operation_plans import OperationPlanService


def _client(tmp_path):
    db_path = initialize_database(tmp_path / "knowledge-points.sqlite3")
    with connect_db(db_path) as conn:
        conn.execute("INSERT INTO questions (question_id, question_type) VALUES ('Q-1', 'single_choice')")
        conn.executemany(
            """INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name, status
            ) VALUES (?, ?, 'T2', 'Mechanics', 'T1', 'Physics', 'active')""",
            [("KP-1", "Force"), ("KP-2", "Motion")],
        )
        conn.execute(
            """INSERT INTO question_knowledge_points
            (link_id, question_id, rank, topic3_id, source, confidence)
            VALUES ('L-1', 'Q-1', 1, 'KP-1', 'manual', 1.0)"""
        )
        conn.commit()
    plans = OperationPlanRepository(db_path)
    service = KnowledgePointService(
        KnowledgePointRepository(db_path),
        OperationPlanService(plans),
    )
    app = FastAPI()
    app.include_router(build_knowledge_points_router(service))
    return TestClient(app), db_path, plans


def _preview_request(topic3_id: str = "KP-2") -> dict:
    return {
        "items": [{"rank": 1, "topic3_id": topic3_id, "source": "manual", "confidence": 1.0}],
        "reason": "Teacher confirmed the replacement.",
    }


def test_knowledge_point_preview_confirm_is_idempotent_and_audited(tmp_path) -> None:
    client, db_path, plans = _client(tmp_path)
    preview = client.post("/api/questions/Q-1/knowledge-points/preview-replace", json=_preview_request())
    assert preview.status_code == 200
    operation_id = preview.json()["operation_plan"]["operation_id"]
    assert plans.get(operation_id).status == "planned"

    confirmed = client.post("/api/questions/knowledge-points/confirm-operation", json={"operation_id": operation_id})
    replay = client.post("/api/questions/knowledge-points/confirm-operation", json={"operation_id": operation_id})
    assert confirmed.json()["status"] == "completed"
    assert replay.json()["idempotent"] is True
    audit_batch_id = confirmed.json()["result"]["audit_batch_id"]
    with connect_db(db_path, writable=False) as conn:
        topic3_id = conn.execute(
            "SELECT topic3_id FROM question_knowledge_points WHERE question_id = 'Q-1'"
        ).fetchone()[0]
        audit = conn.execute(
            "SELECT change_type, reason FROM change_batches WHERE batch_id = ?", (audit_batch_id,)
        ).fetchone()
        item = conn.execute(
            "SELECT before_value_json, after_value_json FROM change_items WHERE batch_id = ?", (audit_batch_id,)
        ).fetchone()
    assert topic3_id == "KP-2"
    assert tuple(audit) == ("knowledge_point_replacement", "Teacher confirmed the replacement.")
    assert json.loads(item[0])[0]["topic3_id"] == "KP-1"
    assert json.loads(item[1])[0]["topic3_id"] == "KP-2"


def test_knowledge_point_confirmation_rejects_version_conflict_before_write(tmp_path) -> None:
    client, db_path, plans = _client(tmp_path)
    operation_id = client.post(
        "/api/questions/Q-1/knowledge-points/preview-replace", json=_preview_request()
    ).json()["operation_plan"]["operation_id"]
    with connect_db(db_path) as conn:
        conn.execute("UPDATE question_knowledge_points SET topic3_id = 'KP-2' WHERE question_id = 'Q-1'")
        conn.commit()

    response = client.post("/api/questions/knowledge-points/confirm-operation", json={"operation_id": operation_id})
    assert response.status_code == 409
    assert plans.get(operation_id).status == "planned"
    with connect_db(db_path, writable=False) as conn:
        topic3_id = conn.execute(
            "SELECT topic3_id FROM question_knowledge_points WHERE question_id = 'Q-1'"
        ).fetchone()[0]
    assert topic3_id == "KP-2"


def test_knowledge_point_preview_never_writes_and_noop_needs_no_confirmation(tmp_path) -> None:
    client, db_path, _ = _client(tmp_path)
    response = client.post(
        "/api/questions/Q-1/knowledge-points/preview-replace",
        json=_preview_request("KP-1"),
    )
    assert response.status_code == 200
    assert response.json()["changed"] is False
    assert response.json()["operation_plan"] is None
    with connect_db(db_path, writable=False) as conn:
        topic3_id = conn.execute(
            "SELECT topic3_id FROM question_knowledge_points WHERE question_id = 'Q-1'"
        ).fetchone()[0]
    assert topic3_id == "KP-1"
