"""Internal data models for batch question writing.

These schemas sit between the service and repository layers.
They are NOT API request/response models — see ``review_save.py`` for those.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuestionRecord(BaseModel):
    """Normalised question record ready for database upsert.

    All list-type fields (options, sub_questions, figures, tags) must be
    Python lists of dicts / strings — the service layer serialises them to
    JSON before passing them to the repository.
    """

    question_id: str = Field(..., min_length=1, description="Unique question identifier")
    question_type: str = Field(default="calculation", min_length=1)
    title: str = Field(default="", description="Stem / body text of the question")
    options: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = Field(default="")
    analysis: str = Field(default="")
    sub_questions: list[dict[str, Any]] = Field(default_factory=list)
    figures: list[dict[str, Any]] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=0, le=5)
    knowledge_point: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="")
    source_raw: str = Field(default="")
    import_batch_id: str | None = None
    source_page: int | None = None
    source_region_id: str | None = None
    raw_text: str | None = None
    review_status: str = Field(default="confirmed")


class QuestionBatchWriteResult(BaseModel):
    """Result returned after a batch write operation."""

    received_count: int = 0
    saved_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    errors: list[str] = Field(default_factory=list)
