from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _TeachingProjectResponseBase(BaseModel):
    """Keep persisted project extensions visible while making the stable fields explicit."""

    model_config = ConfigDict(extra="allow")


class TeachingProjectSummary(BaseModel):
    id: str
    title: str = "未命名教学项目"
    projectType: str = "lesson"
    status: str = "draft"
    contentRevision: int = 0
    questionCount: int = 0
    handoutStatus: str = "not_created"
    slidesStatus: str = "not_created"
    createdAt: str = ""
    updatedAt: str = ""
    versionCount: int = 0


class TeachingProjectListResponse(BaseModel):
    document_kind: Literal["teaching_project"] = "teaching_project"
    items: list[TeachingProjectSummary] = Field(default_factory=list)


class TeachingProjectResponse(_TeachingProjectResponseBase):
    document_kind: Literal["teaching_project"] = "teaching_project"
    id: str
    title: str = "未命名教学项目"
    projectType: str = "lesson"
    status: str = "draft"
    contentRevision: int = 0
    content: dict[str, Any] = Field(default_factory=dict)
    handout: dict[str, Any] = Field(default_factory=dict)
    slides: dict[str, Any] = Field(default_factory=dict)
    createdAt: str = ""
    updatedAt: str = ""
    currentVersion: int = 1
    versions: list[dict[str, Any]] = Field(default_factory=list)
    summary: TeachingProjectSummary | None = None


class TeachingProjectUpsertRequest(BaseModel):
    """A complete project snapshot sent by the web or an MCP client."""

    project: dict[str, Any]
    base_updated_at: str | None = Field(default=None, max_length=120)

    @field_validator("project")
    @classmethod
    def validate_project(cls, value: dict[str, Any]) -> dict[str, Any]:
        project_id = str(value.get("id") or "").strip()
        if not project_id:
            raise ValueError("project.id is required")
        if not isinstance(value.get("content"), dict):
            raise ValueError("project.content must be an object")
        return value


class TeachingProjectArchiveRequest(BaseModel):
    base_updated_at: str | None = Field(default=None, max_length=120)


class TeachingProjectDuplicateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
