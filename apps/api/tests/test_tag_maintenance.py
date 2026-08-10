from __future__ import annotations

import json

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.services.tag_maintenance import (
    diagnose_tag_maintenance,
    maintain_question_tags,
    suggest_question_tags,
)


def test_tag_maintenance_merges_aliases_and_creates_catalog_entries(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "tag-maintenance.sqlite3")
    with connect_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty
            ) VALUES ('q-tag-1', 'alias tag item', 'calculation', 4)
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (question_id, title_text, stem_text, tags_json)
            VALUES ('q-tag-1', 'alias tag item', 'body', '["速度补偿法", "模型题"]')
            """
        )
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty
            ) VALUES ('q-tag-2', 'canonical tag item', 'calculation', 5)
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (question_id, title_text, stem_text, tags_json)
            VALUES ('q-tag-2', 'canonical tag item', 'body', '["配速法"]')
            """
        )
        conn.commit()

    preview = maintain_question_tags(
        merge_map={"配速法": ["速度补偿法"]},
        add_tags=["重力配速法"],
        dry_run=True,
        db_path=db_path,
    )

    assert preview["changed_count"] == 2
    assert preview["requires_confirmation"] is True

    applied = maintain_question_tags(
        merge_map={"配速法": ["速度补偿法"]},
        add_tags=["重力配速法"],
        dry_run=False,
        reason="teacher confirmed tag normalization",
        db_path=db_path,
    )

    assert applied["ok"] is True
    assert applied["changed_count"] == 2
    with connect_db(db_path) as conn:
        tags = json.loads(
            conn.execute(
                "SELECT tags_json FROM question_text_index WHERE question_id = 'q-tag-1'"
            ).fetchone()[0]
        )
        assert tags == ["配速法", "模型题", "重力配速法"]
        alias = conn.execute(
            "SELECT status, description FROM tag_catalog WHERE tag_name = '速度补偿法'"
        ).fetchone()
        assert dict(alias) == {"status": "merged", "description": "Merged into 配速法"}


def test_tag_diagnosis_and_suggestions_use_method_and_content_signals(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "tag-suggestions.sqlite3")
    with connect_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty
            ) VALUES ('q-method-tag', 'method indexed item', 'calculation', 5)
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, analysis_text, tags_json
            ) VALUES (
                'q-method-tag', 'method indexed item',
                '带电小球在磁场中从静止释放。',
                '洛伦兹力分力与重力平衡。',
                '["速度补偿法"]'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO question_method_features (
                question_id, method_id, branch, level, score,
                match_basis, evidence_json, index_version
            ) VALUES (
                'q-method-tag', 'velocity_compensation', 'gravity',
                'structural', 0.97, 'structure', '[]', 'test'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty
            ) VALUES ('q-brake', 'braking trap item', 'calculation', 3)
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, analysis_text, tags_json
            ) VALUES (
                'q-brake', 'braking trap item',
                '汽车刹车做匀减速运动，求第 4 s 内的位移，最后停止。',
                '', '[]'
            )
            """
        )
        conn.commit()

    diagnosis = diagnose_tag_maintenance(db_path=db_path, min_similarity=0.5)
    assert diagnosis["tag_count"] == 1

    suggestions = suggest_question_tags(["q-method-tag", "q-brake"], db_path=db_path)
    by_id = {item["question_id"]: item for item in suggestions["items"]}

    method_tags = {item["tag"] for item in by_id["q-method-tag"]["suggested_tags"]}
    assert {"配速法", "重力配速法"} <= method_tags
    brake_tags = {item["tag"] for item in by_id["q-brake"]["suggested_tags"]}
    assert "刹车陷阱" in brake_tags
