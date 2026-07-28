from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.favorites import (
    BatchFavoriteResponse,
    BatchStarRequest,
    FavoriteAssignRequest,
    FavoriteGroupCreate,
    FavoriteGroupItem,
    FavoriteGroupUpdate,
    FavoriteItemView,
)
from ..services.favorites import FavoritesService


def build_favorites_router(
    service: FavoritesService | None = None,
) -> APIRouter:
    if service is None:
        service = FavoritesService()

    router = APIRouter(prefix="/api/favorites", tags=["favorites"])

    # ── Groups ──────────────────────────────────────────────────

    @router.get("/groups", response_model=list[FavoriteGroupItem], summary="列出所有收藏分组")
    async def list_groups() -> list[FavoriteGroupItem]:
        try:
            return service.list_groups()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/groups", response_model=FavoriteGroupItem, summary="新建收藏分组")
    async def create_group(req: FavoriteGroupCreate) -> FavoriteGroupItem:
        try:
            return service.create_group(req)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.put("/groups/{group_id}", summary="重命名收藏分组")
    async def update_group(group_id: str, req: FavoriteGroupUpdate) -> dict[str, bool]:
        ok = service.update_group(group_id, req)
        if not ok:
            raise HTTPException(status_code=404, detail="分组不存在")
        return {"updated": True}

    @router.delete("/groups/{group_id}", summary="删除收藏分组（题目不移除）")
    async def delete_group(group_id: str) -> dict[str, bool]:
        ok = service.delete_group(group_id)
        if not ok:
            raise HTTPException(status_code=404, detail="分组不存在")
        return {"deleted": True}

    # ── Assign / Batch ───────────────────────────────────────────

    @router.post("/assign", response_model=BatchFavoriteResponse, summary="批量设置分组和星标")
    async def assign(req: FavoriteAssignRequest) -> BatchFavoriteResponse:
        try:
            return service.assign(req)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/batch-star", response_model=BatchFavoriteResponse, summary="批量设置星标")
    async def batch_star(req: BatchStarRequest) -> BatchFavoriteResponse:
        try:
            return service.batch_star(req)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/remove", summary="批量取消收藏")
    async def remove(question_ids: list[str]) -> dict[str, int]:
        try:
            count = service.remove(question_ids)
            return {"removed": count}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Query ────────────────────────────────────────────────────

    @router.get("/items/{question_id}", response_model=FavoriteItemView | None, summary="查询单题收藏信息")
    async def get_item(question_id: str) -> FavoriteItemView | None:
        return service.get_item(question_id)

    @router.get("/items", response_model=list[FavoriteItemView], summary="列出收藏题目")
    async def list_items(
        group_id: str | None = None,
        min_star: int = 0,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FavoriteItemView]:
        items, _ = service.list_favorites(
            group_id=group_id, min_star=min_star, limit=limit, offset=offset
        )
        return items

    @router.get("/ids", summary="获取所有收藏题目 ID 集合")
    async def get_ids() -> list[str]:
        return sorted(service.get_favorite_ids())

    return router
