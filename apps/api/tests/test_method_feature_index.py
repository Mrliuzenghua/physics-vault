from __future__ import annotations

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.services.method_feature_index import (
    ensure_method_feature_index_current,
    method_feature_index_health,
    refresh_question_method_features,
)


def test_method_feature_index_backfills_and_incrementally_refreshes(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "method-index.sqlite3")
    with connect_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, module, topic3
            ) VALUES ('q-method', '经典重力配速题', 'calculation', 5, 'electromagnetism', '圆周运动')
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, analysis_text, tags_json
            ) VALUES (
                'q-method', '经典重力配速题',
                '水平匀强磁场中，带正电小球从O点静止释放，求运动曲线最低点，重力加速度为g。',
                '由洛伦兹力、动能定理和曲率半径求解。', '[]'
            )
            """
        )
        conn.commit()

    built = refresh_question_method_features(["q-method"], db_path=db_path)
    assert built == {"question_count": 1, "feature_count": 1}
    health = method_feature_index_health(db_path=db_path)
    assert health["ready_count"] == 1
    assert health["missing_count"] == 0

    with connect_db(db_path) as conn:
        feature = conn.execute(
            """
            SELECT branch, level FROM question_method_features
            WHERE question_id = 'q-method'
            """
        ).fetchone()
        assert dict(feature) == {"branch": "gravity", "level": "structural"}
        conn.execute(
            """
            UPDATE question_text_index
            SET stem_text = '电子进入匀强磁场，不计电子之间的相互作用及电子的重力。',
                analysis_text = '由洛伦兹力提供向心力。'
            WHERE question_id = 'q-method'
            """
        )
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM question_method_index_state WHERE question_id = 'q-method'"
        ).fetchone()[0] == 0

    refreshed = ensure_method_feature_index_current(db_path=db_path)
    assert refreshed["missing_count"] == 1
    with connect_db(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM question_method_features WHERE question_id = 'q-method'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM question_method_index_state WHERE question_id = 'q-method'"
        ).fetchone()[0] == 1
