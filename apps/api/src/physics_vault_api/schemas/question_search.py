from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    browse = "browse"
    strict = "strict"
    hybrid = "hybrid"
    similar = "similar"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class QuestionSearchParams(BaseModel):
    """Typed container for query-string parameters the router will extract."""

    search_mode: SearchMode = SearchMode.browse
    query: str | None = None
    year: int | None = None
    module: str | None = None
    question_type: str | None = None
    difficulty: str | None = None
    status: str | None = None
    topic1_id: str | None = None
    topic2_id: str | None = None
    topic3_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

    # Extra filters inherited from legacy (kept for compatibility)
    paper_id: str | None = None
    region: str | None = None
    exam_type: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    has_media: bool | None = None
    image_count_min: int = Field(default=0, ge=0)
    is_mistake: bool | None = None


# ---------------------------------------------------------------------------
# Response – single question item
# ---------------------------------------------------------------------------


class QuestionItem(BaseModel):
    """Flattened question view returned in search results."""

    question_id: str
    question_type: str | None = None
    title: str | None = None
    answer: str | None = None
    analysis: str | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    figures: list[dict[str, Any]] = Field(default_factory=list)
    difficulty: str | None = None
    knowledge_point: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    year: int | None = None
    status: str | None = None
    is_mistake: bool = False
    mistake_marked_at: str | None = None
    knowledge_points: list[dict[str, Any]] = Field(default_factory=list)

    # Legacy-compatibility aliases (so the frontend doesn't break)
    canonical_title: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    has_media: bool = False
    image_count: int = 0

    # Scoring fields (populated by hybrid / similar modes)
    similarity: float | None = None
    keyword_match: bool = False
    search_mode: str | None = None
    score: float | None = None


# ---------------------------------------------------------------------------
# Response – search result envelope
# ---------------------------------------------------------------------------


class FacetBlock(BaseModel):
    years: list[int] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    exam_types: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)

    # Extended facets
    topic1_ids: list[str] = Field(default_factory=list)
    topic1_values: list[str] = Field(default_factory=list)
    topic2_ids: list[str] = Field(default_factory=list)
    topic2_values: list[str] = Field(default_factory=list)
    topic3_ids: list[str] = Field(default_factory=list)
    topic3_values: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    items: list[QuestionItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0
    search_mode: str = "browse"
    facets: FacetBlock = Field(default_factory=FacetBlock)


class BatchQuestionFetchRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=200)


class BatchQuestionFetchResponse(BaseModel):
    items: list[QuestionItem] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)


class BatchQuestionDeleteRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=200)


class BatchQuestionDeleteResponse(BaseModel):
    requested_count: int = 0
    deleted_count: int = 0
    missing_ids: list[str] = Field(default_factory=list)


class ReturnQuestionToReviewRequest(BaseModel):
    reason: str | None = None
    reviewer: str | None = None


class ReturnQuestionToReviewResponse(BaseModel):
    question_id: str
    review_id: str | None = None
    status: Literal["queued", "missing"] = "queued"
    message: str = ""


# ---------------------------------------------------------------------------
# Filters / facets response (standalone)
# ---------------------------------------------------------------------------


class FilterFacetsResponse(BaseModel):
    years: list[int] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    exam_types: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)

    # Extended fields for compatibility with legacy frontend
    topic1_ids: list[str] = Field(default_factory=list)
    topic1_values: list[str] = Field(default_factory=list)
    topic2_ids: list[str] = Field(default_factory=list)
    topic2_values: list[str] = Field(default_factory=list)
    topic3_ids: list[str] = Field(default_factory=list)
    topic3_values: list[str] = Field(default_factory=list)
