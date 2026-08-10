import sqlite3
from typing import Any

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_search import QuestionSearchRepository
from physics_vault_api.services.similar_questions import SimilarQuestionsService


class _QuestionRepository:
    def __init__(self) -> None:
        self.requested_ids: list[str] = []

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        self.requested_ids = question_ids
        return [{"question_id": question_ids[0], "canonical_title": "target"}]


def test_source_question_is_loaded_directly_by_id() -> None:
    repository = _QuestionRepository()
    service = SimilarQuestionsService(repository)  # type: ignore[arg-type]

    question = service._get_question("q-250")

    assert repository.requested_ids == ["q-250"]
    assert question == {"question_id": "q-250", "canonical_title": "target"}


def test_same_knowledge_point_uses_structured_bindings_and_ignores_null_legacy_fields(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "similar.sqlite3")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO knowledge_points (topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name) VALUES ('kp-momentum', '动量守恒', 'kp-dynamics', '动量', 'kp-mechanics', '力学')"
        )
        conn.execute(
            "INSERT INTO knowledge_points (topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name) VALUES ('kp-refraction', '折射定律', 'kp-optics-2', '几何光学', 'kp-optics', '光学')"
        )
        for question_id, title in (("q-source", "碰撞中的动量守恒"), ("q-same", "爆炸中的动量守恒"), ("q-other", "光的折射")):
            conn.execute(
                "INSERT INTO questions (question_id, canonical_title, question_type, difficulty) VALUES (?, ?, 'calculation', 3)",
                (question_id, title),
            )
            conn.execute(
                "INSERT INTO question_text_index (question_id, stem_text, tags_json) VALUES (?, ?, '[]')",
                (question_id, title),
            )
        conn.execute("INSERT INTO question_knowledge_points (link_id, question_id, topic3_id, rank) VALUES ('l1', 'q-source', 'kp-momentum', 1)")
        conn.execute("INSERT INTO question_knowledge_points (link_id, question_id, topic3_id, rank) VALUES ('l2', 'q-same', 'kp-momentum', 1)")
        conn.execute("INSERT INTO question_knowledge_points (link_id, question_id, topic3_id, rank) VALUES ('l3', 'q-other', 'kp-refraction', 1)")

    result = SimilarQuestionsService(QuestionSearchRepository(str(db_path))).find_similar(
        "q-source", same_knowledge_point=True, limit=10
    )

    assert result.total_candidates == 2
    assert [item.question_id for item in result.items] == ["q-same"]
