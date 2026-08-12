from __future__ import annotations

import sqlite3

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_search import QuestionSearchRepository


def test_strict_search_can_locate_a_question_by_its_catalog_id(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "question-id-search.sqlite3")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, status
            ) VALUES ('Q00004795', '题干不包含内部编号', 'calculation', 3, '已审核')
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (question_id, title_text, stem_text)
            VALUES ('Q00004795', '题干不包含内部编号', '仅用于验证题号定位')
            """
        )

    rows, total = QuestionSearchRepository(str(db_path)).search_questions(
        search_mode="strict",
        query="Q00004795",
        limit=10,
    )

    assert total == 1
    assert [row["question_id"] for row in rows] == ["Q00004795"]
