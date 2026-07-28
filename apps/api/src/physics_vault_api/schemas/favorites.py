"""Schemas for favorite groups and star ratings."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Favorite Group ──────────────────────────────────────────────────

class FavoriteGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class FavoriteGroupUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)


class FavoriteGroupItem(BaseModel):
    id: str
    name: str
    question_count: int = 0
    sort_order: int = 0
    created_at: str = ""


# ── Star / Group assignment ─────────────────────────────────────────

class FavoriteAssignRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=200)
    group_id: str | None = None  # None = move to "ungrouped"
    star_rating: int | None = Field(default=None, ge=1, le=5)


class BatchStarRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=200)
    star_rating: int = Field(..., ge=1, le=5)


# ── Favorite item view ──────────────────────────────────────────────

class FavoriteItemView(BaseModel):
    question_id: str
    group_id: str | None = None
    group_name: str | None = None
    star_rating: int = 0
    added_at: str = ""


class BatchFavoriteResponse(BaseModel):
    total: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
