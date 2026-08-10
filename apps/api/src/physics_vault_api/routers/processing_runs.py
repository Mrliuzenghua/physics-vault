from __future__ import annotations

from fastapi import APIRouter, Query

from ..schemas.processing_runs import ProcessingRunItem
from ..services.processing_runs import ProcessingRunService


def build_processing_runs_router(service: ProcessingRunService) -> APIRouter:
    """Keep the historical root path stable behind the modular router."""

    router = APIRouter(tags=["processing-runs"])

    @router.get("/processing-runs", response_model=list[ProcessingRunItem])
    def list_processing_runs(
        pipeline_name: str | None = None,
        paper_id: str | None = None,
        status: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[ProcessingRunItem]:
        return service.list(
            pipeline_name=pipeline_name,
            paper_id=paper_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    return router
