from __future__ import annotations

from ..repositories.image_catalog import ImageCatalogRepository
from ..schemas.image_catalog import ImageAssetItem


class ImageCatalogService:
    def __init__(self, repository: ImageCatalogRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        query: str | None,
        paper_id: str | None,
        question_id: str | None,
        year: int | None,
        region: str | None,
        exam_type: str | None,
        topic3: str | None,
        verified: bool | None,
        limit: int,
        offset: int,
    ) -> list[ImageAssetItem]:
        return self._repository.list(
            query=query,
            paper_id=paper_id,
            question_id=question_id,
            year=year,
            region=region,
            exam_type=exam_type,
            topic3=topic3,
            verified=verified,
            limit=limit,
            offset=offset,
        )
