from __future__ import annotations

import json

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.services.method_feedback import record_method_retrieval_feedback


def test_teacher_feedback_confirms_metadata_and_can_suppress_false_match(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "method-feedback.sqlite3")
    with connect_db(db_path) as conn:
        for topic_id, name in (
            ("KP-EM-MAGNETIC-COMBINED", "带电粒子在复合场中的运动"),
            ("KP-EM-MAGNETIC-LORENTZ", "洛伦兹力"),
            ("KP-EM-EFIELD-STRENGTH", "电场强度"),
        ):
            conn.execute(
                """
                INSERT INTO knowledge_points (
                    topic3_id, topic3_name, topic2_id, topic2_name,
                    topic1_id, topic1_name, status
                ) VALUES (?, ?, 'KP-EM-L2', '电磁场', 'KP-EM', '电磁学', 'active')
                """,
                (topic_id, name),
            )
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, module
            ) VALUES ('q-feedback', '教师确认的漏检题', 'calculation', 4, '电磁学')
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, analysis_text, tags_json
            ) VALUES (
                'q-feedback', '教师确认的漏检题', '带电粒子在复合场中运动。',
                '原解析较简略。', '["旧标签"]'
            )
            """
        )
        conn.commit()

    confirmed = record_method_retrieval_feedback(
        question_id="q-feedback",
        method_id="velocity_compensation",
        branch="electric",
        verdict="missed",
        reason="教师确认解析实际采用qvB=qE参考速度",
        db_path=db_path,
    )
    assert confirmed["ok"] is True
    with connect_db(db_path) as conn:
        tags = json.loads(
            conn.execute(
                "SELECT tags_json FROM question_text_index WHERE question_id = 'q-feedback'"
            ).fetchone()[0]
        )
        assert {"旧标签", "配速法", "电场配速法"}.issubset(tags)
        topic_ids = [
            row[0]
            for row in conn.execute(
                """
                SELECT topic3_id FROM question_knowledge_points
                WHERE question_id = 'q-feedback' ORDER BY rank
                """
            ).fetchall()
        ]
        assert topic_ids == [
            "KP-EM-MAGNETIC-COMBINED",
            "KP-EM-MAGNETIC-LORENTZ",
            "KP-EM-EFIELD-STRENGTH",
        ]
        feature = conn.execute(
            """
            SELECT level, match_basis FROM question_method_features
            WHERE question_id = 'q-feedback' AND branch = 'electric'
            """
        ).fetchone()
        assert dict(feature) == {"level": "structural", "match_basis": "teacher_feedback"}

    rejected = record_method_retrieval_feedback(
        question_id="q-feedback",
        method_id="velocity_compensation",
        branch="electric",
        verdict="incorrect",
        reason="教师复核后确认并未采用该方法",
        maintain_metadata=False,
        db_path=db_path,
    )
    assert rejected["ok"] is True
    with connect_db(db_path) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*) FROM question_method_features
            WHERE question_id = 'q-feedback' AND branch = 'electric'
            """
        ).fetchone()[0] == 0
