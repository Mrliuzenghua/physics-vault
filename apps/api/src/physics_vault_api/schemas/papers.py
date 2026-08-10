from __future__ import annotations

from pydantic import BaseModel, Field


class PaperSummary(BaseModel):
    paper_id: str
    year: int | None = None
    exam_type: str
    region: str | None = None
    paper_name: str
    subject: str
    status: str
    question_count: int = 0


class PaperDetail(PaperSummary):
    source_path: str | None = None
    source_format: str | None = None
    notes: str | None = None
    created_at: str
    updated_at: str


class PaperQuestionSummary(BaseModel):
    question_id: str
    canonical_title: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    difficulty: str | None = None
    question_type: str | None = Field(default=None, alias="type")
    status: str
    has_media: bool
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    source: str | None = None
    knowledge_points: list[dict] = Field(default_factory=list)
