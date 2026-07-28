"""Schemas for batch analysis generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BatchGenerateAnalysisRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1, max_length=50)
    style: Literal["classroom_brief", "self_study_full", "exam_standard"] = "classroom_brief"
    include_extension: bool = True
    force_regenerate: bool = Field(
        default=False,
        description="为 True 时跳过已有解析检查，强制重新生成",
    )


class BatchAnalysisItemResult(BaseModel):
    question_id: str
    status: Literal["success", "skipped", "failed"] = "success"
    message: str = ""
    saved_to_db: bool = False


class BatchGenerateAnalysisResponse(BaseModel):
    total: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    results: list[BatchAnalysisItemResult] = Field(default_factory=list)
