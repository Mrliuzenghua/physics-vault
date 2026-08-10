from __future__ import annotations

from fastapi import APIRouter

from ..schemas.embedding_status import EmbeddingStatusItem
from ..services.embedding_status import EmbeddingStatusService


def build_embedding_status_router(service: EmbeddingStatusService) -> APIRouter:
    router = APIRouter(tags=["embedding-status"])

    @router.get("/embeddings/status", response_model=list[EmbeddingStatusItem])
    def list_embedding_status() -> list[EmbeddingStatusItem]:
        return service.list_question_embeddings()

    return router
