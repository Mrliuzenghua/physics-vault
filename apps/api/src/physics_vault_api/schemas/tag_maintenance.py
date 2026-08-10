"""Transport models for confirmation-gated canonical tag maintenance."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from mcp_contracts.src.operation_plan import OperationPlan


class TagMaintenancePreviewRequest(BaseModel):
    model_config = {"extra": "forbid"}

    question_ids: list[str] = Field(default_factory=list, max_length=500)
    add_tags: list[str] = Field(default_factory=list, max_length=8)
    remove_tags: list[str] = Field(default_factory=list, max_length=8)
    merge_map: dict[str, list[str]] = Field(default_factory=dict, max_length=100)
    reason: str = Field(..., min_length=1, max_length=300)
    create_catalog_tags: bool = True


class TagMaintenancePreviewResponse(BaseModel):
    ok: bool
    changed_count: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)
    requires_confirmation: bool = False
    message: str = ""
    database_scope: str = "canonical_preview"
    operation_plan: OperationPlan | None = None


class ConfirmTagMaintenanceOperationRequest(BaseModel):
    """Confirmation cannot override the persisted tags, targets, or reason."""

    model_config = {"extra": "forbid"}

    operation_id: str = Field(..., min_length=1)


class TagMaintenanceOperationExecutionResponse(BaseModel):
    operation_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    idempotent: bool = False
