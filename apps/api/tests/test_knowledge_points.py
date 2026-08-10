from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.knowledge_points import KnowledgePointRepository
from physics_vault_api.routers.knowledge_points import build_knowledge_points_router
from physics_vault_api.services.knowledge_points import KnowledgePointService


def test_knowledge_point_counts_preserve_legacy_path_and_deduplicate_questions(tmp_path) -> None:
    db_path = tmp_path / "knowledge-points.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.executemany(
            "INSERT INTO questions (question_id, question_type) VALUES (?, ?)",
            [("Q-1", "single_choice"), ("Q-2", "single_choice")],
        )
        connection.execute(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("KP-1", "Topic 3", "KP-2", "Topic 2", "KP-3", "Topic 1"),
        )
        connection.executemany(
            "INSERT INTO question_knowledge_points (link_id, question_id, topic3_id, rank) VALUES (?, ?, ?, ?)",
            [("L-1", "Q-1", "KP-1", 1), ("L-2", "Q-2", "KP-1", 1)],
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_knowledge_points_router(
            KnowledgePointService(KnowledgePointRepository(str(db_path)))
        )
    )

    response = TestClient(app).get("/knowledge-points/counts")

    assert response.status_code == 200
    assert response.json() == {"KP-1": 2}

    question_links = TestClient(app).get("/questions/Q-1/knowledge-points")
    assert question_links.status_code == 200
    assert question_links.json()[0]["topic3_id"] == "KP-1"
    assert TestClient(app).get("/questions/missing/knowledge-points").status_code == 404


def test_knowledge_point_list_preserves_legacy_filters(tmp_path) -> None:
    db_path = tmp_path / "knowledge-point-list.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("KP-1", "Force", "T2-1", "Mechanics", "T1-1", "Physics", "active"),
                ("KP-2", "Optics", "T2-2", "Light", "T1-1", "Physics", "inactive"),
            ],
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_knowledge_points_router(
            KnowledgePointService(KnowledgePointRepository(str(db_path)))
        )
    )

    response = TestClient(app).get("/knowledge-points", params={"q": "For", "status": "active"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "topic3_id": "KP-1",
            "topic3_name": "Force",
            "topic2_id": "T2-1",
            "topic2_name": "Mechanics",
            "topic1_id": "T1-1",
            "topic1_name": "Physics",
            "source_chapter": None,
            "status": "active",
            "note": None,
        }
    ]


def test_question_knowledge_point_writes_replace_upsert_and_delete(tmp_path) -> None:
    db_path = tmp_path / "knowledge-point-writes.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type) VALUES (?, ?)",
            ("Q-1", "single_choice"),
        )
        connection.executemany(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("KP-1", "Force", "T2-1", "Mechanics", "T1-1", "Physics"),
                ("KP-2", "Motion", "T2-1", "Mechanics", "T1-1", "Physics"),
            ],
        )
        connection.commit()

    app = FastAPI()
    app.include_router(
        build_knowledge_points_router(
            KnowledgePointService(KnowledgePointRepository(str(db_path)))
        )
    )
    client = TestClient(app)

    replace_response = client.put(
        "/questions/Q-1/knowledge-points",
        json=[
            {"rank": 1, "topic3_id": "KP-1"},
            {"rank": 2, "topic3_id": "KP-2", "note": "secondary"},
        ],
    )

    assert replace_response.status_code == 200
    assert [item["topic3_id"] for item in replace_response.json()] == ["KP-1", "KP-2"]
    assert replace_response.json()[1]["note"] == "secondary"

    upsert_response = client.put(
        "/questions/Q-1/knowledge-points/2",
        json={"topic3_id": "KP-2", "confidence": 0.8},
    )
    assert upsert_response.status_code == 200
    assert upsert_response.json()["confidence"] == 0.8

    delete_response = client.delete("/questions/Q-1/knowledge-points/2")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "deleted"}
    assert client.delete("/questions/Q-1/knowledge-points/1").status_code == 400
