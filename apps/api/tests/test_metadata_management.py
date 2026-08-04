from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.import_tasks import InMemoryImportTaskRepository
from physics_vault_api.services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
    normalize_import_question_metadata,
)
from physics_vault_api.services.metadata_management import MetadataManagementService


def _database(tmp_path: Path) -> Path:
    path = initialize_database(tmp_path / "metadata.sqlite3")
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO papers (paper_id, year, exam_type, region, paper_name)
            VALUES ('paper-1', 2025, '高考', '广东', 'raw paper')
            """
        )
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty,
                primary_paper_id, source
            ) VALUES ('q-1', '万有引力测试', 'single_choice', 2, 'paper-1', '旧显示来源')
            """
        )
        conn.execute(
            """
            INSERT INTO question_text_index (question_id, stem_text, source_text, tags_json)
            VALUES ('q-1', '求卫星环绕速度', '原始导入来源，不可覆盖', '[]')
            """
        )
    return path


def test_knowledge_creation_is_idempotent_and_metadata_updates_are_direct(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    service = MetadataManagementService(db_path)
    point = {
        "topic1_id": "KP-MECH",
        "topic1_name": "力学",
        "topic2_name": "万有引力与航天",
        "topic3_name": "万有引力定律",
        "source_chapter": "必修二",
    }

    first = service.create_knowledge_points([point])
    second = service.create_knowledge_points([point])

    assert first["summary"]["created"] == 1
    assert second["summary"]["existing"] == 1
    topic3_id = first["created"][0]["topic3_id"]

    result = service.batch_update_question_metadata(
        [
            {
                "question_id": "q-1",
                "tags": [" 天体运动 ", "天体运动", "图像法"],
                "topic3_ids": [topic3_id],
                "difficulty": 4,
                "question_type": "multi_choice",
                "source_normalized": "2026年高考·广东卷·物理",
                "year": 2026,
                "region": "广东",
                "exam_type": "高考",
            }
        ],
        reason="统一检索元数据",
    )

    assert result["summary"] == {"received": 1, "updated": 1, "skipped": 0, "failed": 0}
    assert result["reason"] == "统一检索元数据"
    with sqlite3.connect(db_path) as conn:
        question = conn.execute(
            "SELECT difficulty, question_type, source FROM questions WHERE question_id='q-1'"
        ).fetchone()
        text = conn.execute(
            "SELECT source_text, tags_json FROM question_text_index WHERE question_id='q-1'"
        ).fetchone()
        binding = conn.execute(
            "SELECT topic3_id FROM question_knowledge_points WHERE question_id='q-1'"
        ).fetchone()
        paper = conn.execute("SELECT year, region, exam_type FROM papers WHERE paper_id='paper-1'").fetchone()
    assert question == (4, "multi_choice", "2026年高考·广东卷·物理")
    assert text == ("原始导入来源，不可覆盖", '["天体运动", "图像法"]')
    assert binding == (topic3_id,)
    assert paper == (2026, "广东", "高考")


def test_metadata_update_rejects_question_content_and_bad_enums(tmp_path: Path) -> None:
    service = MetadataManagementService(_database(tmp_path))

    result = service.batch_update_question_metadata(
        [
            {"question_id": "q-1", "answer": "A"},
            {"question_id": "q-1", "question_type": "essay"},
        ]
    )

    assert result["summary"]["failed"] == 2
    assert "不允许修改" in result["failed"][0]["error"]
    assert "question_type" in result["failed"][1]["error"]

    invalid_paper = service.batch_update_question_metadata(
        [{"question_id": "q-1", "year": 1800, "region": "广东" * 30}]
    )
    assert invalid_paper["ok"] is False
    assert invalid_paper["summary"]["failed"] == 1


def test_knowledge_suggestions_return_only_existing_topic_ids(tmp_path: Path) -> None:
    service = MetadataManagementService(_database(tmp_path))
    created = service.create_knowledge_points(
        [
            {
                "topic1_id": "KP-MECH",
                "topic1_name": "力学",
                "topic2_name": "万有引力与航天",
                "topic3_name": "万有引力定律",
            }
        ]
    )
    topic3_id = created["created"][0]["topic3_id"]

    result = service.suggest_knowledge_points(
        [{"question_id": "draft-1", "title": "根据万有引力定律计算卫星受到的引力"}]
    )

    assert result["summary"]["matched"] == 1
    assert result["matched"][0]["suggestions"][0]["topic3_id"] == topic3_id
    assert result["matched"][0]["suggestions"][0]["confidence"] == "high"

    weak = service.suggest_knowledge_points([{"question_id": "draft-2", "title": "引力"}])
    assert weak["summary"]["unmatched"] == 1
    assert weak["unmatched"][0]["suggested_parent"]["topic2_name"] == "万有引力与航天"


def test_import_metadata_normalization_extracts_answer_fields() -> None:
    normalized = normalize_import_question_metadata(
        {
            "question_id": "draft-1",
            "question_type": "single_choice",
            "answer": "CD 【难度】0.65 【知识点】万有引力定律",
            "source": "2026广东高考物理",
        }
    )

    assert normalized["answer"] == "CD"
    assert normalized["difficulty"] == 3
    assert normalized["knowledge_point"] == "万有引力定律"
    assert normalized["question_type"] == "multi_choice"
    assert normalized["source"] == "2026年高考·广东卷·物理"
    assert normalized["source_raw"] == "2026广东高考物理"
    assert len(normalized["validation_warnings"]) == 3

    experiment = normalize_import_question_metadata(
        {
            "question_type": "single_choice",
            "title": "（1）测量电阻。\n（2）在测绘小灯泡伏安特性曲线实验中：\n①连接电路；②记录数据；③描点作图。",
            "options": [{"opt": "A", "content": "16.7Ω"}],
            "answer": "1750",
        }
    )
    assert experiment["question_type"] == "experiment"


def test_duplicate_review_tasks_can_be_found_and_terminal_tasks_deleted() -> None:
    repository = InMemoryImportTaskRepository()
    service = ImportPipelineService(
        task_repo=repository,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )
    first = service.create_ai_generated_review_task("1. first", source="same source")
    second = service.create_ai_generated_review_task("1. second", source="same source")

    duplicates = service.find_duplicate_review_tasks()
    result = service.delete_review_tasks([first.task_id])

    assert duplicates["duplicate_group_count"] == 1
    assert duplicates["delete_candidate_count"] == 1
    assert result["deleted"] == [first.task_id]
    assert repository.get(first.task_id) is None
    assert repository.get(second.task_id) is not None


def test_metadata_seed_is_non_destructive_and_repeatable(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "maintenance" / "seed_metadata_catalog.py"
    spec = importlib.util.spec_from_file_location("seed_metadata_catalog_for_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db_path = tmp_path / "seed.sqlite3"

    first = module.seed(db_path)
    second = module.seed(db_path)

    assert first["total_knowledge_points"] >= 60
    assert first["total_tags"] >= 30
    assert second["created_knowledge_points"] == 0
    assert second["created_tags"] == 0
