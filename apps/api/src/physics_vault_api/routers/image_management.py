from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ..schemas.contracts import BooleanMapResponse
from ..schemas.image_management import (
    AddImageRequest,
    AddCachedImageRequest,
    AvailableImageAsset,
    CachedImageAsset,
    CacheUploadResponse,
    ImageListResponse,
    QuestionImageDetail,
    ReorderRequest,
    ReplaceImageRequest,
    UpdateImageRequest,
    ValidationResponse,
)
from ..services.image_management import ImageManagementService


def build_image_management_router(
    service: ImageManagementService | None = None,
) -> APIRouter:
    if service is None:
        service = ImageManagementService()

    router = APIRouter(prefix="/api/questions", tags=["image-management"])

    @router.get("/images/cache", response_model=list[CachedImageAsset], summary="列出临时图片缓存")
    async def list_cache_images(keyword: str = "", limit: int = 200) -> list[CachedImageAsset]:
        return service.list_cache_images(keyword=keyword, limit=limit)

    @router.post("/images/cache-upload", response_model=CacheUploadResponse, summary="上传图片或从 Word 提取图片")
    async def upload_cache_images(files: list[UploadFile] = File(...)) -> CacheUploadResponse:
        try:
            uploads = [(file.filename or "upload", await file.read()) for file in files]
            return service.upload_cache_files(uploads)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            for file in files:
                await file.close()

    @router.get("/{question_id}/images", response_model=ImageListResponse, summary="列出题目所有图片")
    async def list_images(question_id: str) -> ImageListResponse:
        try:
            return service.list_images(question_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/{question_id}/images", response_model=QuestionImageDetail, summary="绑定新图片")
    async def add_image(question_id: str, req: AddImageRequest) -> QuestionImageDetail:
        try:
            return service.add_image(question_id, req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/{question_id}/images/from-cache", response_model=QuestionImageDetail, summary="从图片缓存绑定")
    async def add_cached_image(question_id: str, req: AddCachedImageRequest) -> QuestionImageDetail:
        try:
            return service.add_cached_image(question_id, req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/{question_id}/images/{asset_id}/replace", response_model=QuestionImageDetail, summary="替换图片")
    async def replace_image(question_id: str, asset_id: str, req: ReplaceImageRequest) -> QuestionImageDetail:
        try:
            return service.replace_image(question_id, req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/{question_id}/images/{asset_id}", response_model=BooleanMapResponse, summary="更新图片元数据")
    async def update_image(question_id: str, asset_id: str, req: UpdateImageRequest) -> dict[str, bool]:
        ok = service.update_image(question_id, asset_id, req)
        return {"updated": ok}

    @router.delete("/{question_id}/images/{asset_id}", response_model=BooleanMapResponse, summary="删除图片绑定")
    async def delete_image(question_id: str, asset_id: str) -> dict[str, bool]:
        ok = service.delete_image(question_id, asset_id)
        if not ok:
            raise HTTPException(status_code=404, detail="绑定不存在")
        return {"deleted": True}

    @router.post("/{question_id}/images/reorder", response_model=BooleanMapResponse, summary="调整图片顺序")
    async def reorder_images(question_id: str, req: ReorderRequest) -> dict[str, bool]:
        service.reorder_images(question_id, req)
        return {"reordered": True}

    @router.get("/{question_id}/images/validate", response_model=ValidationResponse, summary="校验占位符一致性")
    async def validate_images(question_id: str) -> ValidationResponse:
        return service.validate(question_id)

    @router.get("/images/available", response_model=list[AvailableImageAsset], summary="列出可用素材")
    async def available_images(keyword: str = "", limit: int = 50) -> list[AvailableImageAsset]:
        return service.available_images(keyword=keyword, limit=limit)

    return router
