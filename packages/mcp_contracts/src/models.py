from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .errors import AppWarning

QuestionType = Literal["single_choice", "multi_choice", "fill", "experiment", "calculation"]
AnalysisStyle = Literal["classroom_brief", "self_study_full", "exam_standard"]
KnowledgeLength = Literal["short", "medium", "long"]
MetadataField = Literal[
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


@dataclass(slots=True)
class QuestionOption:
    opt: str
    content: str


@dataclass(slots=True)
class QuestionFigure:
    fig_uuid: str
    local_path: str
    bbox: tuple[int, int, int, int] | None = None
    caption_text: str | None = None


@dataclass(slots=True)
class SubQuestion:
    sub_id: str
    title: str
    answer: str
    analysis: str


@dataclass(slots=True)
class StandardQuestion:
    question_id: str
    question_type: QuestionType
    title: str
    options: list[QuestionOption] = field(default_factory=list)
    answer: str = ""
    analysis: str = ""
    sub_questions: list[SubQuestion] = field(default_factory=list)
    figures: list[QuestionFigure] = field(default_factory=list)
    difficulty: int | None = None
    knowledge_point: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str | None = None
    import_batch_id: str | None = None


@dataclass(slots=True)
class ParsedRegion:
    region_id: str
    bbox: tuple[int, int, int, int]
    preview_path: str
    status: str = "parsed"


@dataclass(slots=True)
class ParsedPage:
    page_no: int
    image_path: str
    question_regions: list[ParsedRegion] = field(default_factory=list)


@dataclass(slots=True)
class ParsedQuestionDraft(StandardQuestion):
    source_page: int = 0
    source_region_id: str = ""
    raw_text: str = ""
    confidence: float = 0.0


@dataclass(slots=True)
class ParseDocumentInput:
    batch_id: str
    file_path: str
    file_type: Literal["pdf", "docx", "jpg", "jpeg", "png", "webp"]
    mode: Literal["auto", "native_document", "image_document"] = "auto"
    enable_preprocess: bool = True
    enable_region_detection: bool = True
    enable_figure_extraction: bool = True
    enable_table_extraction: bool = True
    formula_format: Literal["latex"] = "latex"
    ignore_headers_footers: bool = True


@dataclass(slots=True)
class ParseDocumentOutput:
    document_type: str
    pages: list[ParsedPage] = field(default_factory=list)
    questions: list[ParsedQuestionDraft] = field(default_factory=list)
    warnings: list[AppWarning] = field(default_factory=list)


@dataclass(slots=True)
class DetectQuestionRegionsInput:
    batch_id: str
    page_image: str
    detect_sub_questions: bool = False
    merge_nearby_blocks: bool = True
    ignore_small_noise: bool = True


@dataclass(slots=True)
class DetectQuestionRegionsOutput:
    page_no: int | None = None
    regions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ParseQuestionRegionInput:
    batch_id: str
    region_id: str
    image_path: str
    extract_figures: bool = True
    extract_tables: bool = True
    formula_format: Literal["latex"] = "latex"


@dataclass(slots=True)
class ParseQuestionRegionOutput:
    question: ParsedQuestionDraft


@dataclass(slots=True)
class GenerateAnalysisInput:
    question: StandardQuestion
    style: AnalysisStyle
    include_extension: bool = True
    allow_figure_refs: bool = True


@dataclass(slots=True)
class GenerateAnalysisOutput:
    question_id: str
    structured: dict[str, str]
    text: str
    warnings: list[AppWarning] = field(default_factory=list)


@dataclass(slots=True)
class GenerateKnowledgeInput:
    knowledge_points: list[str]
    style: str
    length: KnowledgeLength = "medium"
    include_formula: bool = True
    include_common_mistakes: bool = True


@dataclass(slots=True)
class GenerateKnowledgeOutput:
    knowledge_key: str
    title: str
    content: str
    outline: list[str] = field(default_factory=list)
    warnings: list[AppWarning] = field(default_factory=list)


@dataclass(slots=True)
class MetadataTaskItem:
    id: str
    question: str
    knowledgePoints: list[str] = field(default_factory=list)
    catalogIds: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    answer: str = ""
    category: str | None = None
    difficulty: int | None = None
    questionType: str | None = None
    source: str | None = None
    year: str | None = None


@dataclass(slots=True)
class MetadataConstraints:
    knowledge_tree: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    catalog_ids: list[str] = field(default_factory=list)
    difficulty_range: list[int] = field(default_factory=list)
    question_types: list[str] = field(default_factory=list)
    model_types: list[str] = field(default_factory=list)
    experiment_types: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GenerateMetadataInput:
    items: list[MetadataTaskItem]
    fields: list[MetadataField]
    constraints: MetadataConstraints
    only_fill_empty: bool = True
    strict_enum_match: bool = True
    prompt_append: str | None = None


@dataclass(slots=True)
class MetadataTaskResultItem:
    id: str
    knowledgePoints: list[str] | None = None
    catalogIds: list[str] | None = None
    tags: list[str] | None = None
    category: str | None = None
    difficulty: int | None = None
    answer: str | None = None
    questionType: str | None = None
    source: str | None = None
    year: str | None = None
    modelType: str | None = None
    experimentType: str | None = None


@dataclass(slots=True)
class GenerateMetadataOutput:
    items: list[MetadataTaskResultItem]
    warnings: list[AppWarning] = field(default_factory=list)


# ── Question Variant Generation ──

VariantMode = Literal[
    "change_condition",
    "change_question",
    "change_numbers",
    "same_model_new_context",
    "difficulty_up",
    "difficulty_down",
]


@dataclass(slots=True)
class VariantSourceQuestion:
    question_id: str
    question_type: str
    title: str
    options: list[dict[str, str]] = field(default_factory=list)
    answer: str = ""
    analysis: str = ""
    difficulty: int | None = None
    knowledge_point: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str | None = None


@dataclass(slots=True)
class GenerateQuestionVariantsInput:
    source_question: VariantSourceQuestion
    variant_mode: VariantMode
    count: int = 1
    instructions: str | None = None
    target_difficulty: int | None = None
    keep_knowledge_points: bool = True


@dataclass(slots=True)
class VariantQuestion:
    question_type: str
    title: str
    options: list[dict[str, str]] = field(default_factory=list)
    answer: str = ""
    analysis: str = ""
    difficulty: int | None = None
    knowledge_point: str | None = None
    tags: list[str] = field(default_factory=list)
    source: str | None = None
    derived_from_question_id: str | None = None
    variant_mode: str | None = None
    variant_note: str | None = None


@dataclass(slots=True)
class GenerateQuestionVariantsOutput:
    variants: list[VariantQuestion] = field(default_factory=list)
    warnings: list[AppWarning] = field(default_factory=list)


def to_dict(instance: Any) -> dict[str, Any]:
    return asdict(instance)
