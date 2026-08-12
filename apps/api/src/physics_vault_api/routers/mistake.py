"""Mistake marking endpoints — single and batch."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.mistake_service import MistakeService


class BatchMistakeRequest(BaseModel):
    question_ids: list[str] = Field(..., min_length=1)


class MistakeResult(BaseModel):
    question_id: str = ""
    status: str = ""
    message: str = ""


class BatchMistakeResponse(BaseModel):
    total: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


class MistakeCountResponse(BaseModel):
    count: int = 0


def build_mistake_router(service: MistakeService) -> APIRouter:
    router = APIRouter(prefix="/api/questions", tags=["mistake"])

    @router.post("/{question_id}/mistake/mark", response_model=MistakeResult)
    async def mark_mistake(question_id: str) -> MistakeResult:
        try:
            result = service.mark(question_id)
            return MistakeResult(**result)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/{question_id}/mistake/unmark", response_model=MistakeResult)
    async def unmark_mistake(question_id: str) -> MistakeResult:
        try:
            result = service.unmark(question_id)
            return MistakeResult(**result)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/mistake/batch-mark", response_model=BatchMistakeResponse)
    async def batch_mark(payload: BatchMistakeRequest) -> BatchMistakeResponse:
        try:
            result = service.batch_mark(payload.question_ids)
            return BatchMistakeResponse(**result)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/mistake/batch-unmark", response_model=BatchMistakeResponse)
    async def batch_unmark(payload: BatchMistakeRequest) -> BatchMistakeResponse:
        try:
            result = service.batch_unmark(payload.question_ids)
            return BatchMistakeResponse(**result)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/mistakes", response_model=list[str])
    async def list_mistakes() -> list[str]:
        try:
            return service.list_mistakes()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/mistakes/count", response_model=MistakeCountResponse)
    async def count_mistakes() -> MistakeCountResponse:
        try:
            return MistakeCountResponse(count=service.count_mistakes())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
