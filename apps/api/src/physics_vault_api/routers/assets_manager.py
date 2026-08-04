from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.assets_manager import (
    AssetListResponse,
    CacheCleanupPreviewResponse,
    CacheCleanupRequest,
    CleanupPreviewResponse,
    CleanupResponse,
    DeleteAssetResponse,
    StorageAnalysisResponse,
)
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
        source: str = Query(default="all", pattern="^(all|question_bank|import_batch)$"),
        batch_id: str = Query(default=""),
        sort_by: str = Query(default="modified_at", pattern="^(name|modified_at|size_bytes|reference_count)$"),
        sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=60, ge=1, le=200),
        refresh: bool = Query(default=False),
        filter_mode: str = Query(
            default="all",
            pattern="^(all|referenced|unreferenced)$",
            description="筛选模式：all / referenced / unreferenced",
        ),
        keyword: str = Query(default="", description="按文件名或路径搜索"),
    ) -> AssetListResponse:
        try:
            return service.get_asset_list(
                filter_mode=filter_mode,
                keyword=keyword,
                source=source,
                batch_id=batch_id,
                sort_by=sort_by,
                sort_order=sort_order,
                page=page,
                page_size=page_size,
                force_refresh=refresh,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotADirectoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "素材列表加载失败", "detail": str(exc)},
            ) from exc

    @router.get("/cleanup-preview", response_model=CleanupPreviewResponse, summary="Preview safe cleanup")
    async def cleanup_preview() -> CleanupPreviewResponse:
        try:
            return service.get_cleanup_preview()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Cleanup preview failed", "detail": str(exc)},
            ) from exc

    @router.get("/storage-analysis", response_model=StorageAnalysisResponse, summary="Analyze asset storage")
    async def storage_analysis(
        source: str = Query(default="all", pattern="^(all|question_bank|import_batch)$"),
        refresh: bool = Query(default=False),
    ) -> StorageAnalysisResponse:
        try:
            return service.analyze_storage(source=source, force_refresh=refresh)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Storage analysis failed", "detail": str(exc)},
            ) from exc

    @router.get("/cache-cleanup-preview", response_model=CacheCleanupPreviewResponse, summary="Preview import cache cleanup")
    async def cache_cleanup_preview(batch_id: str = Query(default="")) -> CacheCleanupPreviewResponse:
        try:
            return service.get_import_cache_cleanup_preview(batch_id=batch_id)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Cache cleanup preview failed", "detail": str(exc)},
            ) from exc

    @router.post("/cleanup-import-cache", response_model=CleanupResponse, summary="Clear import image cache")
    async def cleanup_import_cache(payload: CacheCleanupRequest) -> CleanupResponse:
        try:
            return service.cleanup_import_cache(batch_id=payload.batch_id or "")
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Cache cleanup failed", "detail": str(exc)},
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
