from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.teaching_projects import (
    TeachingProjectArchiveRequest,
    TeachingProjectDuplicateRequest,
    TeachingProjectListResponse,
    TeachingProjectResponse,
    TeachingProjectUpsertRequest,
)
from ..services.teaching_projects import (
    TeachingProjectConflictError,
    archive_teaching_project,
    duplicate_teaching_project,
    get_teaching_project,
    list_teaching_projects,
    save_teaching_project,
)


def build_teaching_projects_router(
    *,
    prefix: str = "/api/teaching-projects",
    tags: list[str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["teaching-projects"])

    @router.get("", response_model=TeachingProjectListResponse)
    def list_projects(limit: int = Query(default=100, ge=1, le=200)) -> dict:
        return {"document_kind": "teaching_project", "items": list_teaching_projects(limit)}

    @router.get("/{project_id}", response_model=TeachingProjectResponse)
    def get_project(project_id: str) -> dict:
        project = get_teaching_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="教学项目不存在")
        return project

    @router.post("", response_model=TeachingProjectResponse)
    def save_project(request: TeachingProjectUpsertRequest) -> dict:
        try:
            return save_teaching_project(request.project, base_updated_at=request.base_updated_at)
        except TeachingProjectConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_REVISION_CONFLICT", "message": str(exc)}) from exc

    @router.post("/{project_id}/archive", response_model=TeachingProjectResponse)
    def archive_project(project_id: str, request: TeachingProjectArchiveRequest) -> dict:
        try:
            project = archive_teaching_project(project_id, base_updated_at=request.base_updated_at)
        except TeachingProjectConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_REVISION_CONFLICT", "message": str(exc)}) from exc
        if project is None:
            raise HTTPException(status_code=404, detail="教学项目不存在")
        return project

    @router.post("/{project_id}/duplicate", response_model=TeachingProjectResponse)
    def duplicate_project(project_id: str, request: TeachingProjectDuplicateRequest) -> dict:
        project = duplicate_teaching_project(project_id, title=request.title)
        if project is None:
            raise HTTPException(status_code=404, detail="教学项目不存在")
        return project

    return router


def build_mcp_teaching_projects_router() -> APIRouter:
    """Expose the same project contract to MCP-connected automation clients."""
    return build_teaching_projects_router(
        prefix="/api/mcp/teaching-projects",
        tags=["mcp", "teaching-projects"],
    )
