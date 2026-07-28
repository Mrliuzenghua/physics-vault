"""REST endpoints for question annotations (批注)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.annotation_service import AnnotationService


class AnnotationCreate(BaseModel):
    question_id: str = Field(..., min_length=1)
    annotation_type: str = Field(default="text")
    content: str = Field(default="")
    anchor_start: int | None = None
    anchor_end: int | None = None
    anchor_text: str | None = None
    figure_uuid: str | None = None
    color: str = Field(default="#fbbf24")
    author: str = Field(default="教师")
    visibility: str = Field(default="private")


class AnnotationUpdate(BaseModel):
    annotation_type: str | None = None
    content: str | None = None
    anchor_start: int | None = None
    anchor_end: int | None = None
    anchor_text: str | None = None
    figure_uuid: str | None = None
    color: str | None = None
    author: str | None = None
    visibility: str | None = None


def build_annotation_router(service: AnnotationService | None = None) -> APIRouter:
    if service is None:
        service = AnnotationService()

    router = APIRouter(prefix="/api/questions", tags=["annotations"])

    @router.get("/{question_id}/annotations")
    async def list_annotations(question_id: str) -> list[dict[str, Any]]:
        return service.list(question_id)

    @router.post("/{question_id}/annotations")
    async def create_annotation(question_id: str, body: AnnotationCreate) -> dict[str, Any]:
        entry = body.model_dump()
        entry["question_id"] = question_id
        return service.create(entry)

    @router.put("/annotations/{annotation_id}")
    async def update_annotation(annotation_id: str, body: AnnotationUpdate) -> dict[str, Any]:
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            return service.update(annotation_id, patch)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/annotations/{annotation_id}")
    async def delete_annotation(annotation_id: str) -> dict[str, str]:
        try:
            return service.delete(annotation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
