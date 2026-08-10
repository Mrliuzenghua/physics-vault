from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.contracts import BooleanMapResponse
from ..schemas.paper_drafts import (
    PaperDraftListResponse,
    PaperDraftResponse,
    PaperDraftUpsertRequest,
)
from ..services.paper_drafts import PaperDraftConflictError, PaperDraftService


def build_paper_drafts_router(service: PaperDraftService | None = None) -> APIRouter:
    if service is None:
        service = PaperDraftService()

    router = APIRouter(prefix="/api/paper-drafts", tags=["paper-drafts"])

    @router.get("", response_model=PaperDraftListResponse, summary="列出试卷草稿")
    async def list_drafts(
        limit: int = Query(default=30, ge=1, le=100),
    ) -> PaperDraftListResponse:
        try:
            return service.list(limit)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/latest", response_model=PaperDraftResponse | None, summary="读取最近草稿")
    async def get_latest_draft() -> PaperDraftResponse | None:
        try:
            return service.get_latest()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/{draft_id}", response_model=PaperDraftResponse, summary="读取试卷草稿")
    async def get_draft(draft_id: str) -> PaperDraftResponse:
        try:
            return service.get(draft_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("", response_model=PaperDraftResponse, summary="保存试卷草稿")
    async def save_draft(request: PaperDraftUpsertRequest) -> PaperDraftResponse:
        try:
            return service.save(request)
        except PaperDraftConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.delete("/{draft_id}", response_model=BooleanMapResponse, summary="删除试卷草稿")
    async def delete_draft(draft_id: str) -> dict[str, bool]:
        try:
            return {"deleted": service.delete(draft_id)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
