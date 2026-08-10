from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.lesson_documents import (
    SavedHandoutListResponse,
    SavedHandoutRenameRequest,
    SavedHandoutResponse,
    SavedHandoutUpsertRequest,
    SavedHandoutVersionListResponse,
)
from ..services.lesson_documents import (
    get_saved_handout,
    list_saved_handout_versions,
    list_saved_handouts,
    rename_saved_handout,
    restore_saved_handout_version,
    save_saved_handout,
)


def build_lesson_documents_router() -> APIRouter:
    router = APIRouter(prefix="/api/lesson-documents", tags=["lesson-documents"])

    @router.get("/saved-handouts", response_model=SavedHandoutListResponse)
    def list_handouts(limit: int = Query(default=100, ge=1, le=200)) -> dict:
        return {"document_kind": "saved_handout", "items": list_saved_handouts(limit)}

    @router.get("/saved-handouts/{document_id}", response_model=SavedHandoutResponse)
    def get_handout(document_id: str) -> dict:
        document = get_saved_handout(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="已保存讲义不存在")
        return document

    @router.post("/saved-handouts", response_model=SavedHandoutResponse)
    def save_handout(request: SavedHandoutUpsertRequest) -> dict:
        return save_saved_handout(request.lesson_package, source_workbench_id=request.source_workbench_id)

    @router.patch("/saved-handouts/{document_id}", response_model=SavedHandoutResponse)
    def rename_handout(document_id: str, request: SavedHandoutRenameRequest) -> dict:
        document = rename_saved_handout(document_id, request.title)
        if document is None:
            raise HTTPException(status_code=404, detail="已保存讲义不存在")
        return document

    @router.get("/saved-handouts/{document_id}/versions", response_model=SavedHandoutVersionListResponse)
    def list_handout_versions(document_id: str) -> dict:
        versions = list_saved_handout_versions(document_id)
        if versions is None:
            raise HTTPException(status_code=404, detail="已保存讲义不存在")
        return {"document_kind": "saved_handout", "document_id": document_id, "items": versions}

    @router.post("/saved-handouts/{document_id}/versions/{version}/restore", response_model=SavedHandoutResponse)
    def restore_handout_version(document_id: str, version: int) -> dict:
        try:
            document = restore_saved_handout_version(document_id, version)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if document is None:
            raise HTTPException(status_code=404, detail="已保存讲义不存在")
        return document

    return router
