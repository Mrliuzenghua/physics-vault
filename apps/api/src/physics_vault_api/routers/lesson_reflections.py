from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.lesson_reflections import (
    LessonReflectionListResponse,
    LessonReflectionResponse,
    LessonReflectionUpsertRequest,
)
from ..services.lesson_reflections import (
    LessonReflectionConflictError,
    get_lesson_reflection,
    list_lesson_reflections,
    save_lesson_reflection,
)


def build_lesson_reflections_router(
    *,
    prefix: str = "/api/lesson-reflections",
    tags: list[str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["lesson-reflections"])

    @router.get("", response_model=LessonReflectionListResponse)
    def list_reflections(
        project_id: str | None = Query(default=None, max_length=160),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return {"document_kind": "lesson_reflection", "items": list_lesson_reflections(project_id, limit)}

    @router.get("/{reflection_id}", response_model=LessonReflectionResponse)
    def get_reflection(reflection_id: str) -> dict:
        reflection = get_lesson_reflection(reflection_id)
        if reflection is None:
            raise HTTPException(status_code=404, detail="课后复盘不存在")
        return {"document_kind": "lesson_reflection", "reflection": reflection}

    @router.post("", response_model=LessonReflectionResponse)
    def save_reflection(request: LessonReflectionUpsertRequest) -> dict:
        try:
            reflection = save_lesson_reflection(
                request.reflection,
                base_updated_at=request.base_updated_at,
            )
        except LessonReflectionConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "REFLECTION_REVISION_CONFLICT", "message": str(exc)},
            ) from exc
        return {"document_kind": "lesson_reflection", "reflection": reflection}

    return router


def build_mcp_lesson_reflections_router() -> APIRouter:
    """Expose reflection persistence to MCP-connected automation clients."""
    return build_lesson_reflections_router(
        prefix="/api/mcp/lesson-reflections",
        tags=["mcp", "lesson-reflections"],
    )
