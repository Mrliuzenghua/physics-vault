from __future__ import annotations

from contextlib import closing

from ..database import connect_db
from ..paths import default_db_path
from ..schemas.image_catalog import ImageAssetItem


class ImageCatalogRepository:
    """Read-only catalog queries for assets across papers and questions."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

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
        db_path = self._db_path or str(default_db_path())
        verified_value = None if verified is None else int(verified)
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT
                    ia.asset_id, ia.filename, ia.file_path, ia.paper_id, ia.question_id,
                    ia.source_id, COALESCE(qa.role, 'question_figure') AS role,
                    COALESCE(qa.sort_order, 0) AS sort_order, ia.mime_type, ia.width, ia.height,
                    ia.description, ia.extracted_text, ia.image_type, ia.binding_confidence, ia.verified
                FROM image_assets ia
                LEFT JOIN papers p ON p.paper_id = ia.paper_id
                LEFT JOIN questions qn ON qn.question_id = ia.question_id
                LEFT JOIN question_assets qa
                    ON qa.asset_id = ia.asset_id AND qa.question_id = ia.question_id
                WHERE (? IS NULL OR ia.paper_id = ?)
                  AND (? IS NULL OR ia.question_id = ?)
                  AND (? IS NULL OR p.year = ?)
                  AND (? IS NULL OR p.region = ?)
                  AND (? IS NULL OR p.exam_type = ?)
                  AND (? IS NULL OR qn.topic3 = ?)
                  AND (? IS NULL OR ia.verified = ?)
                  AND (
                      ? IS NULL
                      OR ia.filename LIKE '%' || ? || '%'
                      OR ia.description LIKE '%' || ? || '%'
                      OR ia.extracted_text LIKE '%' || ? || '%'
                  )
                ORDER BY ia.updated_at DESC, ia.asset_id DESC
                LIMIT ? OFFSET ?
                """,
                (
                    paper_id, paper_id, question_id, question_id, year, year,
                    region, region, exam_type, exam_type, topic3, topic3,
                    verified_value, verified_value, query, query, query, query,
                    limit, offset,
                ),
            ).fetchall()
        return [ImageAssetItem.model_validate(dict(row)) for row in rows]
