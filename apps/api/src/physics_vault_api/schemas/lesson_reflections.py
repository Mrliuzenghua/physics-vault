from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LessonReflectionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    projectId: str
    projectTitle: str | None = None
    rating: int = Field(default=3, ge=1, le=5)
    completed: bool = False
    highlights: str = ""
    followUp: str = ""
    completedFollowUpTaskIds: list[str] = Field(default_factory=list)
    attendedPages: int = Field(default=0, ge=0)
    createdAt: str = ""
    updatedAt: str = ""


class LessonReflectionListResponse(BaseModel):
    document_kind: Literal["lesson_reflection"] = "lesson_reflection"
    items: list[LessonReflectionItem] = Field(default_factory=list)


class LessonReflectionResponse(BaseModel):
    document_kind: Literal["lesson_reflection"] = "lesson_reflection"
    reflection: LessonReflectionItem


class LessonReflectionUpsertRequest(BaseModel):
    """A complete post-lesson reflection snapshot."""

    reflection: dict[str, Any]
    base_updated_at: str | None = Field(default=None, max_length=120)

    @field_validator("reflection")
    @classmethod
    def validate_reflection(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not str(value.get("id") or "").strip():
            raise ValueError("reflection.id is required")
        if not str(value.get("projectId") or "").strip():
            raise ValueError("reflection.projectId is required")
        return value
