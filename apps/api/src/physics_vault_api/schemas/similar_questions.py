from __future__ import annotations

from pydantic import BaseModel, Field


class SimilarQuestionItem(BaseModel):
    """A single similar question returned by the similarity engine."""

    question_id: str
    question_type: str | None = None
    title: str | None = None
    difficulty: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    similarity_score: float = Field(default=0.0, description="0–100 rule-based similarity score")
    has_media: bool = False
    primary_paper_id: str | None = None


class SimilarQuestionsResponse(BaseModel):
    question_id: str = Field(..., description="The source question ID")
    items: list[SimilarQuestionItem] = Field(default_factory=list)
    total_candidates: int = Field(default=0, description="Number of candidates considered before scoring")
    limit: int = Field(default=10)
