import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_write import QuestionWriteRepository
from physics_vault_api.schemas.review_save import ReviewedQuestionPayload
from physics_vault_api.services.question_write import QuestionWriteService
from physics_vault_api.services.review_save import ReviewSaveService


def test_review_save_persists_review_metadata():
    db_path = Path(".codex-run") / f"review-save-{uuid4().hex}.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path = initialize_database(db_path)
    service = ReviewSaveService(
        QuestionWriteService(QuestionWriteRepository(str(db_path)))
    )

    payload = ReviewedQuestionPayload(
        question_id="draft-q1",
        question_type="single_choice",
        title="如图所示，物体做匀速直线运动。",
        options=[{"opt": "A", "content": "速度不变"}],
        answer="A",
        analysis="匀速直线运动速度大小和方向均不变。",
        figures=[{"fig_uuid": "image_0001", "local_path": "data/assets/questions/q1.png"}],
        difficulty=0,
        knowledge_point="运动学",
        tags=["匀速直线运动", "图像题"],
        source="导入样卷.pdf",
        import_batch_id="batch_test",
        source_page=3,
        source_region_id="region_003_001",
        raw_text="原始 OCR 文本",
        review_status="confirmed",
    )

    result = service.save("task-test", [payload])

    assert result.saved_count == 1
    assert result.failed_count == 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    question = conn.execute(
        "SELECT import_batch_id, origin_page, source, difficulty FROM questions WHERE question_id = ?",
        ("draft-q1",),
    ).fetchone()
    text_index = conn.execute(
        """
        SELECT source_id, title_text, stem_clean_text, figures_json, tags_json, source_text
        FROM question_text_index
        WHERE question_id = ?
        """,
        ("draft-q1",),
    ).fetchone()
    conn.close()

    assert question["import_batch_id"] == "batch_test"
    assert question["origin_page"] == 3
    assert question["source"] == "导入样卷.pdf"
    assert question["difficulty"] == 0
    assert text_index["source_id"] == "region_003_001"
    assert text_index["title_text"].startswith("如图所示")
    assert text_index["stem_clean_text"] == "原始 OCR 文本"
    assert json.loads(text_index["figures_json"])[0]["fig_uuid"] == "image_0001"
    assert json.loads(text_index["tags_json"]) == ["匀速直线运动", "图像题"]
    assert text_index["source_text"] == "导入样卷.pdf"

    updated_payload = payload.model_copy(
        update={
            "source": "人工修正来源",
            "import_batch_id": "batch_test_v2",
            "source_page": 4,
            "analysis": "二次修正解析。",
        }
    )
    updated = service.save("task-test", [updated_payload])
    assert updated.saved_count == 1
    assert updated.failed_count == 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    question = conn.execute(
        "SELECT import_batch_id, origin_page, source FROM questions WHERE question_id = ?",
        ("draft-q1",),
    ).fetchone()
    text_index = conn.execute(
        "SELECT source_text, analysis_text FROM question_text_index WHERE question_id = ?",
        ("draft-q1",),
    ).fetchone()
    conn.close()

    assert question["import_batch_id"] == "batch_test_v2"
    assert question["origin_page"] == 4
    assert question["source"] == "人工修正来源"
    assert text_index["source_text"] == "人工修正来源"
    assert text_index["analysis_text"] == "二次修正解析。"
