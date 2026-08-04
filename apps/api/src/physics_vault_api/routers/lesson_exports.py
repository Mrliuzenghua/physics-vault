from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..schemas.import_pipeline import ImportPipelineTaskResponse
from ..schemas.lesson_exports import LessonExportRequest
from ..services.lesson_exports import LessonExportService, serialize_export_task
from ..services.task_queue import LessonExportDispatcher


def build_lesson_exports_router(
    service: LessonExportService,
    dispatcher: LessonExportDispatcher | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/exports", tags=["lesson-exports"])
    task_dispatcher = dispatcher or LessonExportDispatcher(service)

    def submit(export_format: str, payload: LessonExportRequest) -> ImportPipelineTaskResponse:
        try:
            task = task_dispatcher.submit(export_format, payload)  # type: ignore[arg-type]
        except ValueError as exc:
            code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "too large" in str(exc).lower() else 422
            raise HTTPException(status_code=code, detail=str(exc)) from exc
        return ImportPipelineTaskResponse.model_validate(serialize_export_task(task))

    @router.post("/word", response_model=ImportPipelineTaskResponse)
    def export_word(payload: LessonExportRequest) -> ImportPipelineTaskResponse:
        return submit("word", payload)

    @router.post("/pptx", response_model=ImportPipelineTaskResponse)
    def export_pptx(payload: LessonExportRequest) -> ImportPipelineTaskResponse:
        return submit("pptx", payload)

    return router
