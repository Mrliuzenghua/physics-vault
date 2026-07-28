"""Schemas for collection / directory management and batch question moving."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── Collection tree node ────────────────────────────────────────────

class CollectionNode(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    type: Literal["directory", "topic", "subtopic"] = "directory"
    question_count: int = 0
    children: list["CollectionNode"] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


# ── Create collection ───────────────────────────────────────────────

class CreateCollectionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: str | None = None
    type: Literal["directory", "topic", "subtopic"] = "directory"


class CreateCollectionResponse(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    type: str = "directory"


# ── Batch move questions ────────────────────────────────────────────

class BatchMoveRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=200)
    target_collection_id: str = Field(..., min_length=1)


class BatchMoveItemResult(BaseModel):
    question_id: str
    status: Literal["success", "skipped", "failed"] = "success"
    message: str = ""


class BatchMoveResponse(BaseModel):
    total: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    results: list[BatchMoveItemResult] = Field(default_factory=list)


# ── Remove from collection ──────────────────────────────────────────

class RemoveFromCollectionRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=200)
    collection_id: str = Field(..., min_length=1)
