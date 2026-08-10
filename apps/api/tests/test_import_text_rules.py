from physics_vault_api.services.import_text_rules import (
    extract_generated_knowledge_drafts,
    looks_like_knowledge_review,
    merge_draft_metadata,
    normalize_ai_questions,
    normalize_source_name,
    parse_draft_metadata_result,
    source_extension,
)


def test_normalize_source_name_keeps_non_exam_provenance_and_standardizes_exam_source() -> None:
    assert normalize_source_name("自编练习") == "自编练习"
    assert normalize_source_name("2026 广东高考物理") == "2026年高考·广东卷·物理"


def test_normalize_ai_questions_populates_draft_identity_and_preserves_question_content() -> None:
    questions = normalize_ai_questions(
        [{"stem": "求加速度", "answer": "A", "options": []}],
        batch_id="batch_001",
        source="课堂练习",
    )

    assert questions == [
        {
            "question_id": "batch_001-q0001",
            "question_type": "calculation",
            "title": "求加速度",
            "options": [],
            "answer": "A",
            "analysis": "",
            "sub_questions": [],
            "figures": [],
            "difficulty": None,
            "knowledge_point": "",
            "tags": [],
            "source": "课堂练习",
            "import_batch_id": "batch_001",
            "confidence": None,
            "source_page": None,
            "source_region_id": None,
            "raw_text": None,
            "source_raw": "课堂练习",
        }
    ]
    assert source_extension({"stored_filename": "试卷.DOCX"}) == "docx"


def test_knowledge_draft_rules_preserve_review_boundary_and_warnings() -> None:
    source = "知识点：牛顿第二定律\n定义：合力等于质量与加速度的乘积"

    assert looks_like_knowledge_review(source) is True
    drafts, warnings = extract_generated_knowledge_drafts(source, "batch_002")

    assert drafts[0]["topic3_name"] == "牛顿第二定律"
    assert drafts[0]["status"] == "pending"
    assert warnings == ["已按知识点文本整理为待审核草稿，建议补全章节层级和标准知识点 ID。"]


def test_metadata_patch_rules_only_fill_allowed_empty_fields_without_force_overwrite() -> None:
    parsed = parse_draft_metadata_result(
        {"items": [{"question_id": "draft-1", "knowledgePoints": ["牛顿第二定律"], "tags": ["动力学"]}]}
    )
    merged, changed = merge_draft_metadata(
        {"question_id": "draft-1", "knowledge_point": "", "tags": ["基础"], "source": ""},
        parsed["draft-1"],
        ["knowledge_points", "tags", "source"],
        force_overwrite=False,
    )

    assert changed is True
    assert merged["knowledge_point"] == "牛顿第二定律"
    assert merged["tags"] == ["基础"]
