from __future__ import annotations

from pydantic import BaseModel, Field


class ImportQuestionRequest(BaseModel):
    classification: dict = Field(default_factory=dict)
    source: dict = Field(default_factory=dict)
    content: dict = Field(default_factory=dict)
    images: list[dict] = Field(default_factory=list)
    knowledge_points: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    reviewer: str | None = None
    note: str | None = None


class ImportQuestionResponse(BaseModel):
    question_id: str
    status: str
    knowledge_points_inserted: int
    images_linked: int
    skipped_knowledge_points: list[str] = Field(default_factory=list)
    review_id: str
