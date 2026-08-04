from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PaperDraftItemType = Literal["question", "knowledge", "text", "separator", "page_break"]


class PaperDraftItem(BaseModel):
    id: str
    type: PaperDraftItemType
    position: int = Field(default=0, ge=0)
    question_id: str | None = None
    title: str | None = None
    section_title: str | None = None
    score: float | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class PaperDraftUpsertRequest(BaseModel):
    id: str | None = None
    base_updated_at: str | None = Field(
        default=None,
        description="Last server version seen by the caller; stale saves are rejected.",
    )
    title: str = Field(default="未命名试卷", min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=500)
    source: str = Field(default="compose", max_length=40)
    status: str = Field(default="draft", max_length=40)
    items: list[PaperDraftItem] = Field(default_factory=list, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)


class PaperDraftSummary(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    source: str = "compose"
    status: str = "draft"
    question_count: int = 0
    item_count: int = 0
    total_score: float = 0
    updated_at: str = ""
    created_at: str = ""


class PaperDraftResponse(PaperDraftSummary):
    items: list[PaperDraftItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)


class PaperDraftListResponse(BaseModel):
    items: list[PaperDraftSummary] = Field(default_factory=list)
