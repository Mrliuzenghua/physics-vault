from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _SavedHandoutResponseBase(BaseModel):
    """Expose the durable document envelope without discarding existing package fields."""

    model_config = ConfigDict(extra="allow")


class SavedHandoutSummary(BaseModel):
    id: str
    title: str = "未命名讲义"
    subtitle: str = ""
    document_kind: Literal["saved_handout"] = "saved_handout"
    source_workbench_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    question_count: int = 0
    knowledge_count: int = 0
    node_count: int = 0
    format_template_id: str | None = None
    current_version: int = 1
    version_count: int = 0


class SavedHandoutVersion(BaseModel):
    version: int = 0
    version_id: str = ""
    created_at: str = ""
    title: str = ""
    current: bool = False


class SavedHandoutListResponse(BaseModel):
    document_kind: Literal["saved_handout"] = "saved_handout"
    items: list[SavedHandoutSummary] = Field(default_factory=list)


class SavedHandoutVersionListResponse(BaseModel):
    document_kind: Literal["saved_handout"] = "saved_handout"
    document_id: str
    items: list[SavedHandoutVersion] = Field(default_factory=list)


class SavedHandoutResponse(_SavedHandoutResponseBase):
    id: str
    title: str = "未命名讲义"
    subtitle: str = ""
    document_kind: Literal["saved_handout"] = "saved_handout"
    sourceWorkbenchId: str | None = None
    createdAt: str = ""
    updatedAt: str = ""
    formatTemplateId: str | None = None
    currentVersion: int = 1
    versions: list[dict[str, Any]] = Field(default_factory=list)
    lessonPackage: dict[str, Any] = Field(default_factory=dict)
    summary: SavedHandoutSummary | None = None
    restoredFromVersion: int | None = None


class SavedHandoutUpsertRequest(BaseModel):
    lesson_package: dict[str, Any]
    source_workbench_id: str | None = Field(default=None, max_length=200)


class SavedHandoutRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
