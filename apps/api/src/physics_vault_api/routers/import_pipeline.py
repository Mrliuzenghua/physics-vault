from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ..paths import default_import_batches_dir
from ..schemas.contracts import ObjectMapResponse
from ..schemas.import_pipeline import (
    AiParseDocumentRequest,
    AiParseDocumentResponse,
    AiRefineBatchRequest,
    AiRefineBatchResponse,
    CleanDocumentRequest,
    CleanDocumentResponse,
    ConfirmBatchQuestionsRequest,
    ConfirmBatchQuestionsResponse,
    AiGeneratedReviewRequest,
    AiGeneratedReviewResponse,
    ConvertDocumentRequest,
    ConvertDocumentResponse,
    DeleteReviewTaskResponse,
    DraftMetadataRequest,
    DraftMetadataResponse,
    AiCleanBatchResponse,
    AiStructureBatchResponse,
    ExtractBatchImagesResponse,
    ImportBatchResponse,
    ImportBatchOverviewResponse,
    ImportBatchStatusResponse,
    ImportMediaAsset,
    ImportPipelineTaskResponse,
    PandocBatchResponse,
    ParseStructuredQuestionsRequest,
    ParseStructuredQuestionsResponse,
    RecognizeBatchResponse,
    RetryImportBatchResponse,
    ReviewTaskListItem,
    ReviewTaskListResponse,
    UploadImportFileResponse,
)
from ..services.document_pipeline import ImportPipelineService, import_task_to_response
from ..services.task_queue import ImportTaskDispatcher
from ..repositories.review_drafts import SQLiteReviewDraftRepository


def _safe_upload_name(filename: str) -> str:
    source = Path(filename).name
    stem = Path(source).stem.strip() or "document"
    suffix = Path(source).suffix.lower()
    stem = re.sub(r"[^\w\-.()\u4e00-\u9fff]+", "_", stem, flags=re.UNICODE).strip("._")
    return f"{stem[:80] or 'document'}-{uuid4().hex[:8]}{suffix}"


def build_import_pipeline_router(
    service: ImportPipelineService,
    dispatcher: ImportTaskDispatcher | None = None,
    draft_repository: SQLiteReviewDraftRepository | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/import", tags=["import-pipeline"])
    task_dispatcher = dispatcher or ImportTaskDispatcher(service)

    @router.post("/batches", response_model=ImportBatchResponse)
    async def create_import_batch(file: UploadFile = File(...)) -> ImportBatchResponse:
        content = await file.read()
        result = service.create_batch_from_upload(file.filename or "document", content)
        return ImportBatchResponse.model_validate(result)

    @router.post("/batches/{batch_id}/pandoc", response_model=PandocBatchResponse)
    def run_batch_pandoc(batch_id: str) -> PandocBatchResponse:
        task = service.run_batch_pandoc(batch_id)
        if task.status == "failed":
            raise HTTPException(status_code=400, detail=task.error or "Pandoc conversion failed")
        return PandocBatchResponse.model_validate(task.result)

    @router.post("/batches/{batch_id}/ai-clean", response_model=AiCleanBatchResponse)
    def run_batch_ai_clean(batch_id: str) -> AiCleanBatchResponse:
        task = service.run_batch_ai_clean(batch_id)
        if task.status == "failed":
            raise HTTPException(status_code=400, detail=task.error or "AI cleaning failed")
        return AiCleanBatchResponse.model_validate(task.result)

    @router.post("/batches/{batch_id}/ai-structure", response_model=AiStructureBatchResponse)
    def structure_batch_questions(batch_id: str) -> AiStructureBatchResponse:
        task = service.structure_batch_questions(batch_id)
        if task.status == "failed":
            raise HTTPException(status_code=400, detail=task.error or "Question structuring failed")
        return AiStructureBatchResponse.model_validate(task.result)

    @router.post("/batches/{batch_id}/recognize", response_model=RecognizeBatchResponse)
    async def recognize_batch(batch_id: str) -> RecognizeBatchResponse:
        """Automatically route import by file type.

        Word/text documents: Pandoc unpack -> local cleaner -> local splitter.
        Images/PDF: Qwen/VL OCR model.
        """
        result = await service.recognize_batch(batch_id)
        if result.get("status") == "failed":
            raise HTTPException(status_code=400, detail=result.get("error") or "Import recognition failed")
        return RecognizeBatchResponse.model_validate(result)

    @router.post("/batches/{batch_id}/pandoc-task", response_model=ImportPipelineTaskResponse)
    def queue_batch_pandoc(batch_id: str) -> ImportPipelineTaskResponse:
        task = task_dispatcher.submit_batch_stage("pandoc", batch_id)
        return ImportPipelineTaskResponse.model_validate(import_task_to_response(task))

    @router.post("/batches/{batch_id}/ai-clean-task", response_model=ImportPipelineTaskResponse)
    def queue_batch_ai_clean(batch_id: str) -> ImportPipelineTaskResponse:
        task = task_dispatcher.submit_batch_stage("ai_clean", batch_id)
        return ImportPipelineTaskResponse.model_validate(import_task_to_response(task))

    @router.post("/batches/{batch_id}/ai-structure-task", response_model=ImportPipelineTaskResponse)
    def queue_batch_ai_structure(batch_id: str) -> ImportPipelineTaskResponse:
        task = task_dispatcher.submit_batch_stage("ai_structure", batch_id)
        return ImportPipelineTaskResponse.model_validate(import_task_to_response(task))

    @router.post("/batches/{batch_id}/recognize-task", response_model=ImportPipelineTaskResponse)
    def queue_batch_recognition(batch_id: str) -> ImportPipelineTaskResponse:
        task = task_dispatcher.submit_batch_stage("recognize", batch_id)
        return ImportPipelineTaskResponse.model_validate(import_task_to_response(task))

    @router.get("/task-queue/status", response_model=ObjectMapResponse)
    def get_task_queue_status() -> dict[str, str | bool]:
        return task_dispatcher.status()

    @router.post("/batches/{batch_id}/extract-images", response_model=ExtractBatchImagesResponse)
    def extract_batch_images(batch_id: str) -> ExtractBatchImagesResponse:
        """Extract all reusable images from the source document into the batch cache."""
        result = service.extract_batch_images(batch_id)
        if result.get("status") == "failed":
            raise HTTPException(status_code=400, detail=result.get("error") or "Image extraction failed")
        return ExtractBatchImagesResponse.model_validate(result)

    @router.post("/batches/{batch_id}/ai-refine", response_model=AiRefineBatchResponse)
    def refine_batch_questions(batch_id: str, payload: AiRefineBatchRequest) -> AiRefineBatchResponse:
        """Second-pass AI proofreading on the current question list."""
        result = service.refine_batch_questions(batch_id, payload.questions)
        return AiRefineBatchResponse.model_validate(result)

    @router.post("/batches/{batch_id}/draft-metadata", response_model=DraftMetadataResponse)
    async def complete_draft_metadata(batch_id: str, payload: DraftMetadataRequest) -> DraftMetadataResponse:
        """AI-fill metadata for import draft questions before saving them."""
        result = await service.complete_draft_metadata(
            batch_id=batch_id,
            questions=payload.questions,
            fields=payload.fields,
            force_overwrite=payload.force_overwrite,
        )
        return DraftMetadataResponse.model_validate(result)

    @router.get("/batches/{batch_id}", response_model=ImportBatchStatusResponse)
    def get_batch_status(batch_id: str) -> ImportBatchStatusResponse:
        return ImportBatchStatusResponse.model_validate(service.get_batch_status(batch_id))

    @router.get("/batches", response_model=ImportBatchOverviewResponse)
    def list_import_batches(limit: int = Query(default=80, ge=1, le=200)) -> ImportBatchOverviewResponse:
        """Persisted batch overview for recovery after browser refresh."""
        return ImportBatchOverviewResponse(items=service.list_batch_overview(limit=limit))

    @router.post("/batches/{batch_id}/retry", response_model=RetryImportBatchResponse)
    def retry_import_batch(batch_id: str, use_ai_cleanup: bool = True) -> RetryImportBatchResponse:
        """Retry a failed Word/text batch from its saved source file."""
        return RetryImportBatchResponse.model_validate(
            service.retry_batch(batch_id, use_ai_cleanup=use_ai_cleanup)
        )

    @router.post("/batches/{batch_id}/confirm", response_model=ConfirmBatchQuestionsResponse)
    def confirm_batch_questions(batch_id: str, payload: ConfirmBatchQuestionsRequest) -> ConfirmBatchQuestionsResponse:
        """Receive user-edited questions and expose them as a completed task
        so the review workbench can load them via /review/{taskId}."""
        task = service.confirm_batch_questions(
            batch_id,
            payload.questions,
            media_assets=[asset.model_dump(mode="json") for asset in payload.media_assets],
            expected_input_version=payload.input_version,
        )
        return ConfirmBatchQuestionsResponse(
            task_id=task.task_id,
            batch_id=batch_id,
            question_count=len(payload.questions),
        )

    @router.post("/ai-generated-review", response_model=AiGeneratedReviewResponse)
    def submit_ai_generated_review(payload: AiGeneratedReviewRequest) -> AiGeneratedReviewResponse:
        """Expose AI-generated question text as a review workbench task."""
        task = service.create_ai_generated_review_task(
            source_text=payload.source_text,
            source=payload.source,
            chat_context=payload.chat_context,
            session_id=payload.session_id,
        )
        result = task.result or {}
        return AiGeneratedReviewResponse(
            task_id=task.task_id,
            batch_id=str(result.get("batch_id") or ""),
            question_count=int(result.get("question_count") or 0),
            knowledge_count=int(result.get("knowledge_count") or 0),
            warnings=[str(item) for item in result.get("warnings") or []],
        )

    @router.get("/review-tasks", response_model=ReviewTaskListResponse)
    def list_review_tasks(limit: int = Query(default=80, ge=1, le=200)) -> ReviewTaskListResponse:
        """List persisted tasks that can be opened in the review workbench."""
        tasks = service.list_review_tasks(limit=limit)
        items: list[ReviewTaskListItem] = []
        for task in tasks:
            result = task.result or {}
            summary = task.input_summary or {}
            batch_id = str(result.get("batch_id") or summary.get("batch_id") or "")
            title = str(
                result.get("title")
                or result.get("source")
                or summary.get("source")
                or ("AI 生成审核" if task.task_type == "ai_generated_review" else "导入校对任务")
            )
            items.append(
                ReviewTaskListItem(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    status=task.status,
                    batch_id=batch_id,
                    title=title,
                    question_count=int(result.get("question_count") or summary.get("question_count") or 0),
                    knowledge_count=int(result.get("knowledge_count") or summary.get("knowledge_count") or 0),
                    source=str(result.get("source") or summary.get("source") or ""),
                    created_at=task.created_at.isoformat(),
                    updated_at=task.updated_at.isoformat(),
                    warnings=[str(item) for item in result.get("warnings") or []],
                )
            )
        return ReviewTaskListResponse(items=items)

    @router.delete("/review-tasks/{task_id}", response_model=DeleteReviewTaskResponse)
    def delete_review_task(task_id: str) -> DeleteReviewTaskResponse:
        """Remove one persisted review task from the workbench queue."""
        deleted = service.delete_review_task(task_id)
        if deleted and draft_repository is not None:
            draft_repository.delete(task_id)
        return DeleteReviewTaskResponse(task_id=task_id, deleted=deleted)

    @router.post("/batches/{batch_id}/images", response_model=ImportMediaAsset)
    async def upload_batch_image(batch_id: str, file: UploadFile = File(...)) -> ImportMediaAsset:
        """Upload an extra image into the batch media directory."""
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="空文件")
        asset = service.add_batch_image(batch_id, file.filename or "image.png", content)
        return ImportMediaAsset.model_validate(asset)

    @router.get("/batches/{batch_id}/images", response_model=list[ImportMediaAsset])
    def list_batch_images(batch_id: str) -> list[ImportMediaAsset]:
        """Return every cached image extracted or uploaded for a batch."""
        return [ImportMediaAsset.model_validate(asset) for asset in service.list_batch_images(batch_id)]

    @router.post("/upload", response_model=UploadImportFileResponse)
    async def upload_import_file(file: UploadFile = File(...)) -> UploadImportFileResponse:
        upload_dir = default_import_batches_dir() / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        stored_name = _safe_upload_name(file.filename or "document")
        target = upload_dir / stored_name
        content = await file.read()
        target.write_bytes(content)

        return UploadImportFileResponse(
            original_name=file.filename or stored_name,
            stored_name=stored_name,
            source_path=str(target),
            size=len(content),
        )

    @router.post("/convert", response_model=ConvertDocumentResponse)
    def convert_document(payload: ConvertDocumentRequest) -> ConvertDocumentResponse:
        task = service.convert_document(payload)
        return ConvertDocumentResponse(task=ImportPipelineTaskResponse.model_validate(import_task_to_response(task)))

    @router.post("/clean", response_model=CleanDocumentResponse)
    def clean_document(payload: CleanDocumentRequest) -> CleanDocumentResponse:
        task = service.clean_document(payload)
        return CleanDocumentResponse(task=ImportPipelineTaskResponse.model_validate(import_task_to_response(task)))

    @router.post("/parse", response_model=ParseStructuredQuestionsResponse)
    def parse_structured_questions(payload: ParseStructuredQuestionsRequest) -> ParseStructuredQuestionsResponse:
        task = service.parse_structured_questions(payload)
        return ParseStructuredQuestionsResponse(task=ImportPipelineTaskResponse.model_validate(import_task_to_response(task)))

    @router.post("/ai-parse-document", response_model=AiParseDocumentResponse)
    async def ai_parse_document(payload: AiParseDocumentRequest) -> AiParseDocumentResponse:
        task = await service.ai_parse_document(payload)
        return AiParseDocumentResponse(task=ImportPipelineTaskResponse.model_validate(import_task_to_response(task)))

    @router.get("/tasks/{task_id}", response_model=ImportPipelineTaskResponse)
    def get_import_task(task_id: str) -> ImportPipelineTaskResponse:
        task = service.get_task(task_id)
        return ImportPipelineTaskResponse.model_validate(import_task_to_response(task))

    return router
