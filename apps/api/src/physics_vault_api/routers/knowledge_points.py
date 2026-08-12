from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.contracts import IntegerMapResponse, StringMapResponse
from ..schemas.knowledge_points import (
    ConfirmQuestionKnowledgePointOperationRequest,
    KnowledgePointItem,
    QuestionKnowledgePointBatchItem,
    QuestionKnowledgePointLink,
    QuestionKnowledgePointOperationExecutionResponse,
    QuestionKnowledgePointOperationResult,
    QuestionKnowledgePointReplacePreviewRequest,
    QuestionKnowledgePointReplacePreviewResponse,
    QuestionKnowledgePointUpsert,
)
from ..services.knowledge_points import KnowledgePointService
from ..services.operation_plans import OperationPlanError, OperationPlanVersionConflict


def build_knowledge_points_router(service: KnowledgePointService) -> APIRouter:
    """First modular knowledge-point endpoint; remaining compatibility routes follow here."""

    router = APIRouter(tags=["knowledge-points"])

    @router.get("/knowledge-points", response_model=list[KnowledgePointItem])
    def list_knowledge_points(
        topic1_id: str | None = None,
        topic1_name: str | None = None,
        topic2_id: str | None = None,
        topic2_name: str | None = None,
        q: str | None = Query(default=None, description="Search topic names and ids"),
        status: str | None = None,
        limit: int = Query(default=200, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[KnowledgePointItem]:
        return service.list(
            topic1_id=topic1_id,
            topic1_name=topic1_name,
            topic2_id=topic2_id,
            topic2_name=topic2_name,
            query=q,
            status=status,
            limit=limit,
            offset=offset,
        )

    @router.get("/knowledge-points/counts", response_model=IntegerMapResponse)
    def knowledge_point_counts() -> dict[str, int]:
        return service.question_counts_by_topic3()

    @router.get("/questions/{question_id}/knowledge-points", response_model=list[QuestionKnowledgePointLink])
    def list_question_knowledge_points(question_id: str) -> list[QuestionKnowledgePointLink]:
        links = service.list_for_question(question_id)
        if links is None:
            raise HTTPException(status_code=404, detail="Question not found")
        return links

    @router.put("/questions/{question_id}/knowledge-points", response_model=list[QuestionKnowledgePointLink])
    def replace_question_knowledge_points(question_id: str, payload: list[QuestionKnowledgePointBatchItem]) -> list[QuestionKnowledgePointLink]:
        try:
            links = service.replace_for_question(question_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if links is None:
            raise HTTPException(status_code=404, detail="Question not found")
        return links

    @router.post(
        "/api/questions/{question_id}/knowledge-points/preview-replace",
        response_model=QuestionKnowledgePointReplacePreviewResponse,
    )
    def preview_question_knowledge_point_replacement(
        question_id: str,
        payload: QuestionKnowledgePointReplacePreviewRequest,
    ) -> QuestionKnowledgePointReplacePreviewResponse:
        try:
            result = service.preview_replacement_for_question(question_id, payload.items, payload.reason)
            return QuestionKnowledgePointReplacePreviewResponse.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/api/questions/knowledge-points/confirm-operation",
        response_model=QuestionKnowledgePointOperationExecutionResponse,
    )
    def confirm_question_knowledge_point_replacement(
        payload: ConfirmQuestionKnowledgePointOperationRequest,
    ) -> QuestionKnowledgePointOperationExecutionResponse:
        try:
            result = service.confirm_replacement_operation(payload.operation_id)
            return QuestionKnowledgePointOperationExecutionResponse(
                operation_id=result.operation_id,
                status=result.status,
                result=QuestionKnowledgePointOperationResult.model_validate(result.result) if result.result else None,
                error=result.error,
                idempotent=result.idempotent,
            )
        except OperationPlanVersionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "OPERATION_PLAN_VERSION_CONFLICT", "message": str(exc)},
            ) from exc
        except OperationPlanError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "OPERATION_PLAN_NOT_FOUND", "message": str(exc)},
            ) from exc

    @router.put("/questions/{question_id}/knowledge-points/{rank}", response_model=QuestionKnowledgePointLink)
    def upsert_question_knowledge_point(question_id: str, rank: int, payload: QuestionKnowledgePointUpsert) -> QuestionKnowledgePointLink:
        try:
            link = service.upsert_for_question(question_id, rank, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if link is None:
            raise HTTPException(status_code=404, detail="Question not found")
        return link

    @router.delete("/questions/{question_id}/knowledge-points/{rank}", response_model=StringMapResponse)
    def delete_question_knowledge_point(question_id: str, rank: int) -> dict[str, str]:
        try:
            service.delete_for_question(question_id, rank)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "deleted"}

    return router
