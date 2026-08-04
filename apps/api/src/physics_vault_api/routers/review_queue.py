from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..repositories.review_queue import ReviewQueueRepository


def build_review_queue_router(repository: ReviewQueueRepository) -> APIRouter:
    router = APIRouter(tags=["review-queue"])

    @router.get("/review-queue")
    async def list_review_queue(
        status: str | None = None,
        queue_type: str | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        return repository.list(status=status, queue_type=queue_type, limit=limit)

    @router.get("/api/review-queue")
    async def list_review_queue_api(
        status: str | None = None,
        queue_type: str | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        items = repository.list(status=status, queue_type=queue_type, limit=limit)
        return {"items": items, "total": len(items)}

    return router
