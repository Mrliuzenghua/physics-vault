from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DocumentType = Literal["pdf", "docx", "markdown", "html", "txt", "image"]
TaskStatus = Literal["pending", "running", "completed", "failed"]


class ConvertDocumentRequest(BaseModel):
    source_path: str = Field(..., description="Absolute or project-relative source file path")
    source_type: DocumentType = Field(..., description="Source file type")
    target_format: Literal["markdown", "html", "plain"] = Field(default="markdown")
    output_path: str | None = Field(default=None, description="Optional output path")


class UploadImportFileResponse(BaseModel):
    original_name: str
    stored_name: str
    source_path: str
    size: int


class ImportMediaAsset(BaseModel):
    image_id: str
    filename: str
    relative_path: str
    absolute_path: str
    size: int


class ImportBatchResponse(BaseModel):
    batch_id: str
    original_filename: str
    stored_filename: str
    source_path: str
    relative_source_path: str
    status: str
    created_at: datetime


class PandocBatchResponse(BaseModel):
    task_id: str | None = None
    batch_id: str
    status: str
    markdown_path: str
    relative_markdown_path: str
    media_dir: str
    relative_media_dir: str
    image_count: int
    images: list[ImportMediaAsset] = Field(default_factory=list)
    markdown_preview: str
    text: str


class AiCleanBatchResponse(BaseModel):
    task_id: str | None = None
    batch_id: str
    status: str
    cleaned_markdown_path: str
    relative_cleaned_markdown_path: str
    cleaned_preview: str
    text: str
    cleaned_by: str = "local_cleaner"
    warnings: list[str] = Field(default_factory=list)


class AiStructureBatchResponse(BaseModel):
    task_id: str | None = None
    batch_id: str
    status: str
    question_count: int
    questions: list[dict] = Field(default_factory=list)
    raw_json_path: str
    normalized_json_path: str
    structured_by: str = "local_markdown_parser"
    ai_refined_count: int = 0
    media_assets: list[ImportMediaAsset] = Field(default_factory=list)


class RecognizeBatchResponse(BaseModel):
    """Unified import result after automatic pipeline routing."""

    task_id: str | None = None
    batch_id: str
    status: str
    pipeline: Literal["word_pandoc_local", "word_pandoc_deepseek", "vision_qwen_ocr"]
    source_type: str
    question_count: int
    questions: list[dict] = Field(default_factory=list)
    media_assets: list[ImportMediaAsset] = Field(default_factory=list)
    markdown_preview: str = ""
    structured_by: str = ""
    ai_refined_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ExtractBatchImagesResponse(BaseModel):
    batch_id: str
    status: str
    source_type: str
    image_count: int = 0
    media_dir: str = ""
    relative_media_dir: str = ""
    media_assets: list[ImportMediaAsset] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AiRefineBatchRequest(BaseModel):
    """Questions submitted for a second AI proofreading pass on the review page."""

    questions: list[dict] = Field(..., description="Current question list to AI-refine")


class AiRefineBatchResponse(BaseModel):
    batch_id: str
    status: str
    refined_count: int = 0
    questions: list[dict] = Field(default_factory=list)
    refined_by: str = "local_only"
    warnings: list[str] = Field(default_factory=list)


class DraftMetadataRequest(BaseModel):
    questions: list[dict] = Field(..., min_length=1, description="Current import draft questions")
    fields: list[str] = Field(default_factory=lambda: ["knowledge_points", "tags", "source"])
    force_overwrite: bool = False


class DraftMetadataResponse(BaseModel):
    batch_id: str
    status: str = "ok"
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    questions: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfirmBatchQuestionsRequest(BaseModel):
    """Edited questions confirmed by the user in the import workbench."""
    questions: list[dict] = Field(..., description="User-edited question list")


class ConfirmBatchQuestionsResponse(BaseModel):
    task_id: str
    batch_id: str
    question_count: int


class ImportBatchStatusResponse(BaseModel):
    batch_id: str
    status: str
    original_filename: str | None = None
    source_path: str | None = None
    markdown_path: str | None = None
    image_count: int = 0
    question_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class CleanDocumentRequest(BaseModel):
    source_text: str = Field(..., description="Raw extracted document text")
    normalize_whitespace: bool = True
    strip_headers_footers: bool = True
    normalize_math_delimiters: bool = True
    remove_blank_lines: bool = True


class ParseStructuredQuestionsRequest(BaseModel):
    source_text: str = Field(..., description="Cleaned document text")
    import_batch_id: str = Field(..., description="Import batch identifier")
    source_path: str | None = None
    source_type: DocumentType = "markdown"


class ImportPipelineTaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    input_summary: dict[str, str | int | None] = Field(default_factory=dict)
    result: dict | None = None
    error: str | None = None


class ConvertDocumentResponse(BaseModel):
    task: ImportPipelineTaskResponse


class CleanDocumentResponse(BaseModel):
    task: ImportPipelineTaskResponse


class ParseStructuredQuestionsResponse(BaseModel):
    task: ImportPipelineTaskResponse


class AiParseDocumentRequest(BaseModel):
    """Request for MCP-backed AI document parsing (image/PDF/scan recognition)."""
    batch_id: str = Field(..., description="Import batch identifier")
    file_path: str = Field(..., description="Path to the image or PDF file to parse")
    file_type: Literal["pdf", "jpg", "jpeg", "png", "webp"] = Field(..., description="Source file type")
    mode: Literal["auto", "native_document", "image_document"] = "auto"
    enable_preprocess: bool = True
    enable_region_detection: bool = True
    enable_figure_extraction: bool = True
    enable_table_extraction: bool = True
    formula_format: Literal["latex"] = "latex"
    ignore_headers_footers: bool = True


class AiParseDocumentResponse(BaseModel):
    task: ImportPipelineTaskResponse
