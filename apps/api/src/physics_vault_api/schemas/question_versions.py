from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuestionVersionSummary(BaseModel):
    version_id: str
    question_id: str
    version_number: int
    change_summary: str | None = None
    modified_by: str = "system"
    source: str = "manual"
    created_at: str


class QuestionVersionDetail(QuestionVersionSummary):
    snapshot: dict[str, Any]


class VersionRollbackRequest(BaseModel):
    modified_by: str = Field(default="teacher", min_length=1)


class VersionRollbackResponse(BaseModel):
    ok: bool = True
    question_id: str
    restored_from_version: str
    restored_version_number: int
    message: str
