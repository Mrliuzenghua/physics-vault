"""Schemas for batch metadata completion (knowledge_points, tags, source)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MetadataField = Literal["knowledge_points", "tags", "source"]
MetadataMode = Literal["ai", "manual", "mixed"]


class ManualValues(BaseModel):
    """Explicit values to apply when mode is 'manual' or 'mixed'."""
    knowledge_points: str | None = Field(default=None, description="知识点文本")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    source: str | None = Field(default=None, description="来源文本")


class BatchMetadataRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1)
    fields: list[MetadataField] = Field(..., min_length=1)
    mode: MetadataMode = "manual"
    manual_values: ManualValues | None = None
    force_overwrite: bool = Field(
        default=False,
        description="True=覆盖已有值，False=仅补全空字段",
    )


class BatchMetadataItemResult(BaseModel):
    question_id: str
    status: Literal["updated", "skipped", "failed"]
    updated_fields: list[str] = Field(default_factory=list)
    message: str = ""


class BatchMetadataResponse(BaseModel):
    total: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[BatchMetadataItemResult] = Field(default_factory=list)
