from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QuestionOptionPayload(BaseModel):
    opt: str
    content: str


class QuestionFigurePayload(BaseModel):
    fig_uuid: str
    local_path: str
    bbox: tuple[int, int, int, int] | None = None
    caption_text: str | None = None


class SubQuestionPayload(BaseModel):
    sub_id: str
    title: str
    answer: str = ""
    analysis: str = ""


class StandardQuestionPayload(BaseModel):
    question_id: str
    question_type: Literal["single_choice", "multi_choice", "fill", "experiment", "calculation"]
    title: str
    options: list[QuestionOptionPayload] = Field(default_factory=list)
    answer: str = ""
    analysis: str = ""
    sub_questions: list[SubQuestionPayload] = Field(default_factory=list)
    figures: list[QuestionFigurePayload] = Field(default_factory=list)
    difficulty: int | None = None
    knowledge_point: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    import_batch_id: str | None = None


class ParseDocumentRequest(BaseModel):
    batch_id: str
    file_path: str
    file_type: Literal["pdf", "docx", "jpg", "jpeg", "png", "webp"]
    mode: Literal["auto", "native_document", "image_document"] = "auto"
    enable_preprocess: bool = True
    enable_region_detection: bool = True
    enable_figure_extraction: bool = True
    enable_table_extraction: bool = True
    ignore_headers_footers: bool = True


class DetectQuestionRegionsRequest(BaseModel):
    batch_id: str
    page_image: str
    detect_sub_questions: bool = False
    merge_nearby_blocks: bool = True
    ignore_small_noise: bool = True


class ParseQuestionRegionRequest(BaseModel):
    batch_id: str
    region_id: str
    image_path: str
    extract_figures: bool = True
    extract_tables: bool = True


class GenerateAnalysisRequest(BaseModel):
    question: StandardQuestionPayload
    style: Literal["classroom_brief", "self_study_full", "exam_standard"] = "classroom_brief"
    include_extension: bool = True
    allow_figure_refs: bool = True


class GenerateKnowledgeRequest(BaseModel):
    knowledge_points: list[str]
    style: str = "teacher_handout"
    length: Literal["short", "medium", "long"] = "medium"
    include_formula: bool = True
    include_common_mistakes: bool = True


class MetadataTaskItemPayload(BaseModel):
    id: str
    question: str
    knowledgePoints: list[str] = Field(default_factory=list)
    catalogIds: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    answer: str = ""
    category: str | None = None
    difficulty: int | None = None
    questionType: str | None = None
    source: str | None = None
    year: str | None = None


class MetadataConstraintsPayload(BaseModel):
    knowledge_tree: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    catalog_ids: list[str] = Field(default_factory=list)
    difficulty_range: list[int] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    model_types: list[str] = Field(default_factory=list)
    experiment_types: list[str] = Field(default_factory=list)


class GenerateMetadataRequest(BaseModel):
    items: list[MetadataTaskItemPayload]
    fields: list[
        Literal[
            "knowledgePoints",
            "tags",
            "category",
            "catalogIds",
            "answer",
            "difficulty",
            "questionType",
            "source",
            "year",
            "modelType",
            "experimentType",
        ]
    ]
    constraints: MetadataConstraintsPayload = Field(default_factory=MetadataConstraintsPayload)
    only_fill_empty: bool = True
    strict_enum_match: bool = True
    prompt_append: str | None = None


class McpStatusResponse(BaseModel):
    enabled: bool
    mode: str
    working_directory: str | None = None
    tools: dict[str, str]
    vl_available: bool = False
    llm_available: bool = False
    http_mode: bool = False
    vl_model: str | None = None
    llm_model: str | None = None
    last_checked_at: str | None = None


class McpTaskResponse(BaseModel):
    ok: bool = True
    data: dict[str, Any]
