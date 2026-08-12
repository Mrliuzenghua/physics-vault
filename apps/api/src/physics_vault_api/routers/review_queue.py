from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..repositories.review_queue import ReviewQueueRepository
from ..schemas.contracts import ObjectListResponse


def build_review_queue_router(repository: ReviewQueueRepository) -> APIRouter:
    router = APIRouter(tags=["review-queue"])

    @router.get("/review-queue", response_model=ObjectListResponse)
    async def list_review_queue(
        status: str | None = None,
        queue_type: str | None = None,
        limit: int = Query(default=80, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        return repository.list(status=status, queue_type=queue_type, limit=limit)

    return router
