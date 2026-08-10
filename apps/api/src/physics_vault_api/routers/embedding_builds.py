from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.embedding_builds import EmbeddingBuildRequest, EmbeddingBuildResponse
from ..services.embedding_builds import EmbeddingBuildService


def build_embedding_builds_router(service: EmbeddingBuildService) -> APIRouter:
    router = APIRouter(tags=["embedding-builds"])
    @router.post("/embeddings/questions/build", response_model=EmbeddingBuildResponse)
    def build_question_embeddings(payload: EmbeddingBuildRequest) -> EmbeddingBuildResponse:
        try: return service.build(payload)
        except RuntimeError as exc: raise HTTPException(status_code=500, detail=str(exc)) from exc
    return router
