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
    difficulty: int | None = Field(default=None, ge=1, le=5)
    knowledge_point: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="")
    import_batch_id: str | None = None
    review_status: str = Field(
        default="confirmed",
        description="Review status: confirmed / modified / pending / discarded",
    )


class SaveReviewedQuestionsRequest(BaseModel):
    task_id: str = Field(..., description="Import task ID this review session belongs to")
    questions: list[ReviewedQuestionPayload] = Field(
        ..., min_length=1, description="Questions to save"
    )


class SaveResultItem(BaseModel):
    draft_question_id: str
    saved_question_id: str | None = None
    error: str | None = None


class SaveReviewedQuestionsResponse(BaseModel):
    saved_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    results: list[SaveResultItem] = Field(default_factory=list)
