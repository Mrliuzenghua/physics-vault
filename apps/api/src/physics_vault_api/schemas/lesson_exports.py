from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class LessonExportRequest(BaseModel):
    """An immutable browser composition snapshot submitted for server export."""

    lesson_package: dict[str, Any]
    include_answers: bool = False
    include_analysis: bool = False
    file_name: str | None = Field(default=None, max_length=160)

    @field_validator("lesson_package")
    @classmethod
    def validate_lesson_package(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not str(value.get("id") or "").strip():
            raise ValueError("lesson_package.id is required")
        if not isinstance(value.get("questions", []), list):
            raise ValueError("lesson_package.questions must be a list")
        if not isinstance(value.get("nodes", []), list):
            raise ValueError("lesson_package.nodes must be a list")
        return value
