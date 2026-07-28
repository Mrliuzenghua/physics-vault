from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.assets_manager import AssetListResponse, CleanupResponse, DeleteAssetResponse
from ..services.assets_manager import AssetsManagerService


def build_assets_manager_router(
    service: AssetsManagerService | None = None,
) -> APIRouter:
    if service is None:
        service = AssetsManagerService()

    router = APIRouter(prefix="/api/assets", tags=["assets-manager"])

    @router.get(
        "",
        response_model=AssetListResponse,
        summary="获取素材列表及引用状态",
    )
    async def list_assets(
        filter_mode: str = Query(
            default="all",
            pattern="^(all|referenced|unreferenced)$",
            description="筛选模式：all / referenced / unreferenced",
        ),
        keyword: str = Query(default="", description="按文件名或路径搜索"),
    ) -> AssetListResponse:
        try:
            return service.get_asset_list(filter_mode=filter_mode, keyword=keyword)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotADirectoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "素材列表加载失败", "detail": str(exc)},
            ) from exc

    @router.post(
        "/cleanup-unreferenced",
        response_model=CleanupResponse,
        summary="批量清理无引用素材",
    )
    async def cleanup_unreferenced() -> CleanupResponse:
        try:
            return service.cleanup_unreferenced()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "清理失败", "detail": str(exc)},
            ) from exc

    @router.delete(
        "/{filename:path}",
        response_model=DeleteAssetResponse,
        summary="删除单个素材文件",
    )
    async def delete_asset(filename: str) -> DeleteAssetResponse:
        try:
            result = service.delete_single(filename)
            if not result.success:
                raise HTTPException(status_code=400, detail=result.message)
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "删除失败", "detail": str(exc)},
            ) from exc

    return router
