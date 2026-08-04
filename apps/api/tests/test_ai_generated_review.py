from physics_vault_api.repositories.import_tasks import InMemoryImportTaskRepository
from physics_vault_api.services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
)


def test_ai_generated_question_can_be_exposed_as_review_task():
    service = ImportPipelineService(
        task_repo=InMemoryImportTaskRepository(),
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )

    task = service.create_ai_generated_review_task(
        source_text=(
            "1. 如图所示，卫星绕地球做匀速圆周运动。已知轨道半径为 $r$，"
            "地球质量为 $M$，求卫星线速度大小。\n"
            "A. $\\sqrt{GM/r}$\n"
            "B. $GM/r$\n"
            "答案：A\n"
            "解析：由 $GMm/r^2=mv^2/r$ 得 $v=\\sqrt{GM/r}$。"
        ),
        source="AI 题库助手 · 测试",
        chat_context="用户：生成一道万有引力题",
        session_id="test-session",
    )

    result = task.result or {}
    question = result["questions"][0]

    assert task.status == "completed"
    assert result["question_count"] == 1
    assert question["question_type"] == "single_choice"
    assert question["answer"] == "A"
    assert question["options"][0]["opt"] == "A"
    assert "GMm" in question["analysis"]
    assert question["source"] == "AI 题库助手 · 测试"
