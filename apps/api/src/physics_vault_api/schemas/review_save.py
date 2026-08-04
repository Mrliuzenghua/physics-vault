from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReviewedQuestionPayload(BaseModel):
    """A single question submitted from the review workbench."""

    question_id: str = Field(..., description="Draft question ID from the review page")
    question_type: str = Field(default="calculation")
    title: str = Field(default="")
    options: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = Field(default="")
    analysis: str = Field(default="")
    sub_questions: list[dict[str, Any]] = Field(default_factory=list)
    figures: list[dict[str, Any]] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=0, le=5)
    knowledge_point: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="")
    import_batch_id: str | None = None
    source_page: int | None = None
    source_region_id: str | None = None
    source_bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    raw_text: str | None = None
    review_status: str = Field(
        default="confirmed",
        description="Review status: confirmed / modified / pending / discarded",
    )


class SaveReviewedQuestionsRequest(BaseModel):
    task_id: str = Field(..., description="Import task ID this review session belongs to")
    questions: list[ReviewedQuestionPayload] = Field(
        ..., min_length=1, description="Questions to save"
    )


class ReviewedKnowledgePayload(BaseModel):
    """A single knowledge-point draft submitted from the review workbench."""

    draft_id: str = Field(..., description="Draft knowledge ID from the review page")
    topic3_id: str = Field(default="")
    topic3_name: str = Field(default="")
    topic2_id: str = Field(default="")
    topic2_name: str = Field(default="")
    topic1_id: str = Field(default="")
    topic1_name: str = Field(default="")
    source_chapter: str = Field(default="")
    definition: str = Field(default="")
    formula: str = Field(default="")
    key_summary: str = Field(default="")
    error_prone: str = Field(default="")
    example_analysis: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    raw_text: str = Field(default="")
    review_status: str = Field(default="confirmed")


class SaveReviewedKnowledgeRequest(BaseModel):
    task_id: str = Field(..., description="Import task ID this review session belongs to")
    knowledge_drafts: list[ReviewedKnowledgePayload] = Field(..., min_length=1)


class SaveResultItem(BaseModel):
    draft_question_id: str
    saved_question_id: str | None = None
    error: str | None = None


class SaveReviewedQuestionsResponse(BaseModel):
    saved_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    results: list[SaveResultItem] = Field(default_factory=list)


class SaveReviewedKnowledgeResponse(BaseModel):
    saved_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    results: list[SaveResultItem] = Field(default_factory=list)


class ReviewDraftState(BaseModel):
    drafts: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_drafts: list[dict[str, Any]] = Field(default_factory=list)
    task_meta: dict[str, Any] = Field(default_factory=dict)
    current_index: int = Field(default=0, ge=0)
    queue: str = Field(default="risk")


class SaveReviewDraftRequest(BaseModel):
    base_version: int = Field(default=0, ge=0)
    state: ReviewDraftState


class RestoreReviewDraftRequest(BaseModel):
    base_version: int = Field(..., ge=0)
    version: int = Field(..., ge=1)


class ReviewDraftResponse(BaseModel):
    task_id: str
    version: int
    state: ReviewDraftState
    updated_at: str


class ReviewDraftLookupResponse(BaseModel):
    draft: ReviewDraftResponse | None = None


class ReviewDraftVersionListResponse(BaseModel):
    items: list[ReviewDraftResponse] = Field(default_factory=list)
