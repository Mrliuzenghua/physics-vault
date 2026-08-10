from __future__ import annotations

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database


def test_question_text_edit_marks_ready_embedding_stale(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "embedding-invalidation.sqlite3")
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO questions (question_id, canonical_title, question_type)
            VALUES ('Q-1', 'Before', 'calculation')
            """
        )
        connection.execute(
            "INSERT INTO question_text_index (question_id, stem_text) VALUES ('Q-1', 'Before')"
        )
        connection.execute(
            """
            INSERT INTO embeddings (
                embedding_id, owner_type, owner_id, vector_type, model_name,
                dimensions, vector_json, status
            ) VALUES ('E-1', 'question', 'Q-1', 'semantic_search',
                      'text-embedding-v3', 2, '[1,0]', 'ready')
            """
        )
        connection.execute(
            "UPDATE question_text_index SET stem_text = 'After' WHERE question_id = 'Q-1'"
        )
        status = connection.execute(
            "SELECT status FROM embeddings WHERE embedding_id = 'E-1'"
        ).fetchone()["status"]

    assert status == "stale"


def test_knowledge_binding_edit_marks_ready_embedding_stale(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "knowledge-invalidation.sqlite3")
    with connect_db(db_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type) VALUES ('Q-1', 'calculation')"
        )
        connection.execute(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name
            ) VALUES ('T3-1', '碰撞', 'T2-1', '动量', 'T1-1', '力学')
            """
        )
        connection.execute(
            """
            INSERT INTO embeddings (
                embedding_id, owner_type, owner_id, vector_type, model_name,
                dimensions, vector_json, status
            ) VALUES ('E-1', 'question', 'Q-1', 'semantic_search',
                      'text-embedding-v3', 2, '[1,0]', 'ready')
            """
        )
        connection.execute(
            """
            INSERT INTO question_knowledge_points (
                link_id, question_id, topic3_id, rank
            ) VALUES ('L-1', 'Q-1', 'T3-1', 1)
            """
        )
        status = connection.execute(
            "SELECT status FROM embeddings WHERE embedding_id = 'E-1'"
        ).fetchone()["status"]

    assert status == "stale"
