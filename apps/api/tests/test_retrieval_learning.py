from __future__ import annotations

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.services.method_feedback import record_method_retrieval_feedback
from physics_vault_api.services.retrieval_learning import (
    build_method_retrieval_learning_report,
    load_method_feedback_constraints,
)


def test_teacher_feedback_becomes_benchmark_constraint_and_metadata_candidate(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "retrieval-learning.sqlite3")
    with connect_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, module
            ) VALUES ('q-learn-positive', 'teacher confirmed method problem', 'calculation', 5, 'electromagnetism')
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, analysis_text, tags_json
            ) VALUES (
                'q-learn-positive', 'teacher confirmed method problem',
                'charged body released from rest in a uniform magnetic field',
                'teacher says this is the gravity branch of velocity compensation',
                '[]'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, module
            ) VALUES ('q-learn-negative', 'teacher rejected method problem', 'calculation', 4, 'electromagnetism')
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, analysis_text, tags_json
            ) VALUES (
                'q-learn-negative', 'teacher rejected method problem',
                'charged particle in magnetic field',
                'plain circular motion only',
                '[]'
            )
            """
        )
        conn.commit()

    record_method_retrieval_feedback(
        question_id="q-learn-positive",
        method_id="velocity_compensation",
        branch="gravity",
        verdict="missed",
        reason="teacher-confirmed missed positive",
        maintain_metadata=False,
        db_path=db_path,
    )
    record_method_retrieval_feedback(
        question_id="q-learn-negative",
        method_id="velocity_compensation",
        branch="gravity",
        verdict="incorrect",
        reason="teacher-confirmed hard negative",
        maintain_metadata=False,
        db_path=db_path,
    )

    constraints = load_method_feedback_constraints(db_path=db_path)
    assert constraints == [
        {
            "case_id": "teacher_feedback_velocity_compensation_gravity",
            "method_id": "velocity_compensation",
            "branch": "gravity",
            "query": "重力配速法",
            "positive_question_ids": ["q-learn-positive"],
            "negative_question_ids": ["q-learn-negative"],
        }
    ]

    report = build_method_retrieval_learning_report(db_path=db_path)

    assert report["learning_loop"]["teacher_feedback_is_benchmark"] is True
    assert report["learning_loop"]["positive_feedback_cases"] == 1
    assert report["learning_loop"]["negative_feedback_cases"] == 1
    assert report["metadata_maintenance_candidates"][0]["question_id"] == "q-learn-positive"
    assert report["metadata_maintenance_candidates"][0]["severity"] == "high"
    assert "配速法" in report["metadata_maintenance_candidates"][0]["missing_tags"]
