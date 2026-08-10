from __future__ import annotations

from fastapi import APIRouter, Query

from ..schemas.image_catalog import ImageAssetItem
from ..services.image_catalog import ImageCatalogService


def build_image_catalog_router(service: ImageCatalogService) -> APIRouter:
    """Preserve the legacy catalog URL while separating it from asset mutation APIs."""

    router = APIRouter(tags=["image-catalog"])

    @router.get("/images", response_model=list[ImageAssetItem])
    def list_images(
        q: str | None = Query(default=None, description="Search in filename, description, extracted_text"),
        paper_id: str | None = None,
        question_id: str | None = None,
        year: int | None = None,
        region: str | None = None,
        exam_type: str | None = None,
        topic3: str | None = None,
        verified: bool | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[ImageAssetItem]:
        return service.list(
            query=q, paper_id=paper_id, question_id=question_id, year=year,
            region=region, exam_type=exam_type, topic3=topic3, verified=verified,
            limit=limit, offset=offset,
        )

    return router
