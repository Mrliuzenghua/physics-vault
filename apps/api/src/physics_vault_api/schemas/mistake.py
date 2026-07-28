"""Schemas for mistake marking operations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MarkMistakeRequest(BaseModel):
    question_id: str = Field(..., description="题目 ID")
    is_mistake: bool = Field(..., description="True=标记错题, False=取消错题")


class BatchMarkMistakeRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=500, description="题目 ID 列表")
    is_mistake: bool = Field(..., description="True=批量标记, False=批量取消")


class MistakeItemResult(BaseModel):
    question_id: str
    status: str  # "marked", "unmarked", "skipped", "failed"
    message: str | None = None


class BatchMarkMistakeResponse(BaseModel):
    total: int
    success: int
    skipped: int
    failed: int
    items: list[MistakeItemResult] = Field(default_factory=list)


class MistakeStatsResponse(BaseModel):
    total_questions: int
    mistake_count: int
    recent_7d_count: int = 0
