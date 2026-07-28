from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..paths import default_import_batches_dir
from ..schemas.import_pipeline import (
    AiParseDocumentRequest,
    AiParseDocumentResponse,
    AiRefineBatchRequest,
    AiRefineBatchResponse,
    CleanDocumentRequest,
    CleanDocumentResponse,
    ConfirmBatchQuestionsRequest,
    ConfirmBatchQuestionsResponse,
    ConvertDocumentRequest,
    ConvertDocumentResponse,
    DraftMetadataRequest,
    DraftMetadataResponse,
    AiCleanBatchResponse,
    AiStructureBatchResponse,
    ExtractBatchImagesResponse,
    ImportBatchResponse,
    ImportBatchStatusResponse,
    ImportMediaAsset,
    ImportPipelineTaskResponse,
    PandocBatchResponse,
    ParseStructuredQuestionsRequest,
    ParseStructuredQuestionsResponse,
    RecognizeBatchResponse,
    UploadImportFileResponse,
)
from ..services.document_pipeline import ImportPipelineService, import_task_to_response


def _safe_upload_name(filename: str) -> str:
    source = Path(filename).name
    stem = Path(source).stem.strip() or "document"
    suffix = Path(source).suffix.lower()
    stem = re.sub(r"[^\w\-.()\u4e00-\u9fff]+", "_", stem, flags=re.UNICODE).strip("._")
    return f"{stem[:80] or 'document'}-{uuid4().hex[:8]}{suffix}"


def build_import_pipeline_router(service: ImportPipelineService) -> APIRouter:
    router = APIRouter(prefix="/api/import", tags=["import-pipeline"])

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

    @router.post("/batches/{batch_id}/confirm", response_model=ConfirmBatchQuestionsResponse)
    def confirm_batch_questions(batch_id: str, payload: ConfirmBatchQuestionsRequest) -> ConfirmBatchQuestionsResponse:
        """Receive user-edited questions and expose them as a completed task
        so the review workbench can load them via /review/{taskId}."""
        task = service.confirm_batch_questions(batch_id, payload.questions)
        return ConfirmBatchQuestionsResponse(
            task_id=task.task_id,
            batch_id=batch_id,
            question_count=len(payload.questions),
        )

    @router.post("/batches/{batch_id}/images", response_model=ImportMediaAsset)
    async def upload_batch_image(batch_id: str, file: UploadFile = File(...)) -> ImportMediaAsset:
        """Upload an extra image into the batch media directory."""
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="空文件")
        asset = service.add_batch_image(batch_id, file.filename or "image.png", content)
        return ImportMediaAsset.model_validate(asset)

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
