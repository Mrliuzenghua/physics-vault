from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.assets_manager import (
    AssetListResponse,
    CacheCleanupPreviewResponse,
    CacheCleanupRequest,
    CleanupPreviewResponse,
    CleanupResponse,
    ConfirmOperationPlanRequest,
    DeleteAssetResponse,
    OperationPlanExecutionResponse,
    StorageAnalysisResponse,
)
from ..services.assets_manager import AssetsManagerService
from ..services.operation_plans import OperationPlanError, OperationPlanService, OperationPlanVersionConflict, build_asset_cleanup_plan
from ..repositories.operation_plans import OperationPlanRepository


def build_assets_manager_router(
    service: AssetsManagerService | None = None,
    operation_plan_service: OperationPlanService | None = None,
) -> APIRouter:
    if service is None:
        service = AssetsManagerService()
    if operation_plan_service is None:
        operation_plan_service = OperationPlanService(OperationPlanRepository())

    router = APIRouter(prefix="/api/assets", tags=["assets-manager"])

    @router.get(
        "",
        response_model=AssetListResponse,
        summary="获取素材列表及引用状态",
    )
    def list_assets(
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
            preview = service.get_cleanup_preview()
            plan = build_asset_cleanup_plan(
                action="assets.cleanup_unreferenced", scope=preview.scope,
                candidate_count=preview.candidate_count, reclaimable_bytes=preview.reclaimable_bytes,
                protected_count=preview.protected_count,
            )
            operation_plan_service.save_preview(plan)
            return preview.model_copy(
                update={
                    "operation_plan": plan
                }
            )
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
            preview = service.get_import_cache_cleanup_preview(batch_id=batch_id)
            plan = build_asset_cleanup_plan(action="assets.cleanup_import_cache", scope="import_cache", batch_id=preview.batch_id, candidate_count=preview.candidate_count, reclaimable_bytes=preview.reclaimable_bytes, protected_count=preview.protected_count)
            operation_plan_service.save_preview(plan)
            return preview.model_copy(
                update={
                    "operation_plan": plan
                }
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Cache cleanup preview failed", "detail": str(exc)},
            ) from exc

    @router.post("/cleanup-import-cache", response_model=CleanupResponse, summary="Clear import image cache")
    async def cleanup_import_cache(payload: CacheCleanupRequest) -> CleanupResponse:
        try:
            return service.cleanup_import_cache(batch_id=payload.batch_id or "").model_copy(update={"compatibility_mode": True, "migration_message": "Use confirm-operation with operation_id."})
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Cache cleanup failed", "detail": str(exc)},
            ) from exc

    @router.get(
        "/unused-cache-preview",
        response_model=CacheCleanupPreviewResponse,
        summary="Preview cleanup of all unused assets",
    )
    async def unused_cache_preview(batch_id: str = Query(default="")) -> CacheCleanupPreviewResponse:
        try:
            preview = service.get_unused_cache_cleanup_preview(batch_id=batch_id)
            plan = build_asset_cleanup_plan(action="assets.cleanup_unused_cache", scope="unused_cache", batch_id=preview.batch_id, candidate_count=preview.candidate_count, reclaimable_bytes=preview.reclaimable_bytes, protected_count=preview.protected_count)
            operation_plan_service.save_preview(plan)
            return preview.model_copy(
                update={
                    "operation_plan": plan
                }
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Unused cache preview failed", "detail": str(exc)},
            ) from exc

    @router.post(
        "/cleanup-unused-cache",
        response_model=CleanupResponse,
        summary="Clear all unused assets",
    )
    async def cleanup_unused_cache(payload: CacheCleanupRequest) -> CleanupResponse:
        try:
            return service.cleanup_unused_cache(batch_id=payload.batch_id or "").model_copy(update={"compatibility_mode": True, "migration_message": "Use confirm-operation with operation_id."})
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "Unused cache cleanup failed", "detail": str(exc)},
            ) from exc

    @router.post(
        "/cleanup-unreferenced",
        response_model=CleanupResponse,
        summary="批量清理无引用素材",
    )
    async def cleanup_unreferenced() -> CleanupResponse:
        try:
            return service.cleanup_unreferenced().model_copy(update={"compatibility_mode": True, "migration_message": "Use confirm-operation with operation_id."})
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

    @router.post("/confirm-operation", response_model=OperationPlanExecutionResponse)
    async def confirm_operation(payload: ConfirmOperationPlanRequest) -> OperationPlanExecutionResponse:
        try:
            result = operation_plan_service.execute(
                payload.operation_id,
                version_reader=lambda plan: _preview_for_plan(service, plan).expected_version or "",
                executor=lambda plan: _run_plan(service, plan).model_dump(),
            )
            return OperationPlanExecutionResponse(
                operation_id=result.operation_id, status=result.status,
                result=CleanupResponse.model_validate(result.result) if result.result else None,
                error=result.error, idempotent=result.idempotent,
            )
        except OperationPlanVersionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "OPERATION_PLAN_VERSION_CONFLICT", "message": str(exc)}) from exc
        except OperationPlanError as exc:
            raise HTTPException(status_code=404, detail={"code": "OPERATION_PLAN_NOT_FOUND", "message": str(exc)}) from exc

    return router


def _preview_for_plan(service: AssetsManagerService, plan):
    target = plan.targets[0].id
    if plan.action == "assets.cleanup_unreferenced":
        p = service.get_cleanup_preview()
        return build_asset_cleanup_plan(action=plan.action, scope=p.scope, candidate_count=p.candidate_count, reclaimable_bytes=p.reclaimable_bytes, protected_count=p.protected_count)
    if plan.action == "assets.cleanup_import_cache":
        p = service.get_import_cache_cleanup_preview(batch_id=target)
        return build_asset_cleanup_plan(action=plan.action, scope="import_cache", batch_id=p.batch_id, candidate_count=p.candidate_count, reclaimable_bytes=p.reclaimable_bytes, protected_count=p.protected_count)
    if plan.action == "assets.cleanup_unused_cache":
        p = service.get_unused_cache_cleanup_preview(batch_id=target)
        return build_asset_cleanup_plan(action=plan.action, scope="unused_cache", batch_id=p.batch_id, candidate_count=p.candidate_count, reclaimable_bytes=p.reclaimable_bytes, protected_count=p.protected_count)
    raise OperationPlanError("unsupported operation action")


def _run_plan(service: AssetsManagerService, plan) -> CleanupResponse:
    target = plan.targets[0].id
    if plan.action == "assets.cleanup_unreferenced":
        return service.cleanup_unreferenced()
    if plan.action == "assets.cleanup_import_cache":
        return service.cleanup_import_cache(batch_id=target)
    if plan.action == "assets.cleanup_unused_cache":
        return service.cleanup_unused_cache(batch_id=target)
    raise OperationPlanError("unsupported operation action")
