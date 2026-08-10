from physics_vault_api.services.document_pipeline import StructuredQuestionParsingService as PipelineParser
from physics_vault_api.services.import_question_parser import ImportQuestionParser, StructuredQuestionParsingService


def test_document_pipeline_keeps_structured_parser_import_compatible() -> None:
    assert PipelineParser is StructuredQuestionParsingService


def test_import_question_parser_turns_ai_question_text_into_review_draft() -> None:
    questions, warnings = ImportQuestionParser().parse_ai_generated_questions(
        "1. 已知物体做匀加速直线运动，求加速度。\nA. 1 m/s²\nB. 2 m/s²\n答案：B\n解析：由速度变化率可得。",
        batch_id="batch_parser",
        source="AI 测试",
    )

    assert warnings
    assert questions[0]["question_id"] == "batch_parser_q0001"
    assert questions[0]["question_type"] == "single_choice"
    assert questions[0]["answer"] == "B"
