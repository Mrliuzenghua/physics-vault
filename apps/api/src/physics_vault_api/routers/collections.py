from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.contracts import IntegerMapResponse
from ..schemas.collections import (
    BatchMoveRequest,
    BatchMoveResponse,
    CollectionNode,
    CreateCollectionRequest,
    CreateCollectionResponse,
    RemoveFromCollectionRequest,
)
from ..services.collections import CollectionsService


def build_collections_router(
    service: CollectionsService | None = None,
) -> APIRouter:
    if service is None:
        service = CollectionsService()

    router = APIRouter(prefix="/api/collections", tags=["collections"])

    @router.get(
        "/tree",
        response_model=list[CollectionNode],
        summary="获取完整目录/专题树",
    )
    async def get_tree() -> list[CollectionNode]:
        try:
            return service.get_tree()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post(
        "",
        response_model=CreateCollectionResponse,
        summary="新建目录/专题",
    )
    async def create_collection(
        request: CreateCollectionRequest,
    ) -> CreateCollectionResponse:
        try:
            return service.create(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post(
        "/batch-move",
        response_model=BatchMoveResponse,
        summary="批量移动题目到目录/专题",
    )
    async def batch_move(request: BatchMoveRequest) -> BatchMoveResponse:
        try:
            return service.batch_move(request.question_ids, request.target_collection_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post(
        "/remove-questions",
        response_model=IntegerMapResponse,
        summary="从目录/专题中移出题目",
    )
    async def remove_questions(
        request: RemoveFromCollectionRequest,
    ) -> dict[str, int]:
        try:
            count = service.remove_from_collection(
                request.question_ids, request.collection_id
            )
            return {"removed": count}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get(
        "/questions/{question_id}",
        response_model=list[CollectionNode],
        summary="查询题目所属目录/专题",
    )
    async def get_question_collections(question_id: str) -> list[CollectionNode]:
        try:
            return service.get_for_question(question_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
