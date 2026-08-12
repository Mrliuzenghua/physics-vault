from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.contracts import ObjectMapResponse
from ..repositories.review_drafts import ReviewDraftConflictError, ReviewDraftSnapshot, SQLiteReviewDraftRepository

from ..schemas.review_save import (
    ConfirmReviewDraftOperationRequest,
    ReviewDraftOperationExecutionResponse,
    ReviewDraftOperationPreviewResponse,
    RestoreReviewDraftPreviewRequest,
    SaveReviewedKnowledgeRequest,
    SaveReviewedKnowledgeResponse,
    RestoreReviewDraftRequest,
    ReviewDraftLookupResponse,
    ReviewDraftResponse,
    ReviewDraftVersionListResponse,
    SaveReviewDraftRequest,
    SaveReviewedQuestionsRequest,
    SaveReviewedQuestionsResponse,
)
from ..repositories.operation_plans import OperationPlanRepository
from ..services.operation_plans import (
    OperationPlanError,
    OperationPlanService,
    OperationPlanVersionConflict,
    build_review_draft_plan,
)
from ..services.review_save import ReviewSaveService


def build_review_save_router(
    service: ReviewSaveService | None = None,
    draft_repository: SQLiteReviewDraftRepository | None = None,
    operation_plan_service: OperationPlanService | None = None,
) -> APIRouter:
    if service is None:
        service = ReviewSaveService()
    if draft_repository is None:
        draft_repository = SQLiteReviewDraftRepository()
    if operation_plan_service is None:
        operation_plan_service = OperationPlanService(OperationPlanRepository())

    router = APIRouter(prefix="/api/review", tags=["review-save"])

    def draft_response(snapshot: ReviewDraftSnapshot) -> ReviewDraftResponse:
        return ReviewDraftResponse(
            task_id=snapshot.task_id,
            version=snapshot.version,
            state=snapshot.state,
            updated_at=snapshot.updated_at.isoformat(),
        )

    def conflict_response(exc: ReviewDraftConflictError) -> HTTPException:
        current = draft_response(exc.current).model_dump(mode="json") if exc.current else None
        return HTTPException(
            status_code=409,
            detail={"code": "review_draft_conflict", "message": "草稿已被其他页面更新", "current": current},
        )

    @router.get("/drafts/{task_id}", response_model=ReviewDraftLookupResponse)
    async def get_review_draft(task_id: str) -> ReviewDraftLookupResponse:
        snapshot = draft_repository.get(task_id)
        return ReviewDraftLookupResponse(draft=draft_response(snapshot) if snapshot else None)

    @router.put("/drafts/{task_id}", response_model=ReviewDraftResponse)
    async def save_review_draft(task_id: str, payload: SaveReviewDraftRequest) -> ReviewDraftResponse:
        try:
            snapshot = draft_repository.save(task_id, payload.base_version, payload.state.model_dump(mode="json"))
        except ReviewDraftConflictError as exc:
            raise conflict_response(exc) from exc
        return draft_response(snapshot)

    @router.get("/drafts/{task_id}/versions", response_model=ReviewDraftVersionListResponse)
    async def list_review_draft_versions(
        task_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> ReviewDraftVersionListResponse:
        return ReviewDraftVersionListResponse(
            items=[draft_response(item) for item in draft_repository.list_versions(task_id, limit=limit)]
        )

    @router.post(
        "/drafts/{task_id}/delete-preview",
        response_model=ReviewDraftOperationPreviewResponse,
        summary="Preview review draft deletion",
    )
    async def preview_delete_review_draft(task_id: str) -> ReviewDraftOperationPreviewResponse:
        snapshot = _require_draft(draft_repository, task_id)
        plan = build_review_draft_plan(
            action="review_drafts.delete",
            task_id=task_id,
            current_version=snapshot.version,
        )
        operation_plan_service.save_preview(plan)
        return _preview_response(plan, snapshot.version)

    @router.post(
        "/drafts/{task_id}/restore-preview",
        response_model=ReviewDraftOperationPreviewResponse,
        summary="Preview review draft version restoration",
    )
    async def preview_restore_review_draft(
        task_id: str,
        payload: RestoreReviewDraftPreviewRequest,
    ) -> ReviewDraftOperationPreviewResponse:
        snapshot = _require_draft(draft_repository, task_id)
        if not any(item.version == payload.version for item in draft_repository.list_versions(task_id)):
            raise HTTPException(status_code=404, detail="找不到指定草稿版本")
        plan = build_review_draft_plan(
            action="review_drafts.restore",
            task_id=task_id,
            current_version=snapshot.version,
            restore_version=payload.version,
        )
        operation_plan_service.save_preview(plan)
        return _preview_response(plan, snapshot.version)

    @router.delete("/drafts/{task_id}", response_model=ObjectMapResponse)
    async def delete_review_draft(task_id: str) -> dict[str, bool | str]:
        draft_repository.delete(task_id)
        return {"task_id": task_id, "deleted": True}

    @router.post("/drafts/{task_id}/restore", response_model=ReviewDraftResponse)
    async def restore_review_draft(task_id: str, payload: RestoreReviewDraftRequest) -> ReviewDraftResponse:
        try:
            snapshot = draft_repository.restore(task_id, payload.version, payload.base_version)
        except ReviewDraftConflictError as exc:
            raise conflict_response(exc) from exc
        if snapshot is None:
            raise HTTPException(status_code=404, detail="找不到指定草稿版本")
        return draft_response(snapshot)

    @router.post(
        "/drafts/confirm-operation",
        response_model=ReviewDraftOperationExecutionResponse,
        summary="Confirm a persisted review draft operation",
    )
    async def confirm_review_draft_operation(
        payload: ConfirmReviewDraftOperationRequest,
    ) -> ReviewDraftOperationExecutionResponse:
        try:
            result = operation_plan_service.execute(
                payload.operation_id,
                version_reader=lambda plan: _current_review_draft_version(draft_repository, plan),
                executor=lambda plan: _run_review_draft_plan(draft_repository, plan),
            )
            return ReviewDraftOperationExecutionResponse(
                operation_id=result.operation_id,
                status=result.status,
                result=result.result,
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

    @router.post(
        "/save",
        response_model=SaveReviewedQuestionsResponse,
        summary="保存校对结果入库",
        description=(
            "将校对工作台中已确认的题目批量写入题库数据库。"
            "仅 review_status 为 'confirmed' 的题目会被保存；"
            "discarded / pending / modified 状态的题目会被跳过。"
        ),
    )
    async def save_reviewed(payload: SaveReviewedQuestionsRequest) -> SaveReviewedQuestionsResponse:
        try:
            return service.save(payload.task_id, payload.questions)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "数据库不可用，请检查数据库文件是否存在", "detail": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "保存失败，请稍后重试", "detail": str(exc)},
            ) from exc

    @router.post(
        "/save-knowledge",
        response_model=SaveReviewedKnowledgeResponse,
        summary="保存审核通过的知识点入库",
    )
    async def save_reviewed_knowledge(payload: SaveReviewedKnowledgeRequest) -> SaveReviewedKnowledgeResponse:
        try:
            return service.save_knowledge(payload.task_id, payload.knowledge_drafts)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "数据库不可用，请检查数据库文件是否存在", "detail": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "保存知识点失败，请稍后重试", "detail": str(exc)},
            ) from exc

    return router


def _require_draft(
    draft_repository: SQLiteReviewDraftRepository,
    task_id: str,
) -> ReviewDraftSnapshot:
    snapshot = draft_repository.get(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="找不到审核草稿")
    return snapshot


def _preview_response(
    plan: object,
    draft_version: int,
) -> ReviewDraftOperationPreviewResponse:
    operation_plan = plan
    return ReviewDraftOperationPreviewResponse(
        task_id=_review_plan_target(operation_plan, "review_draft"),
        action=operation_plan.action,
        draft_version=draft_version,
        summary=operation_plan.summary,
        expires_at=operation_plan.expires_at.isoformat(),
        reversible=operation_plan.reversible,
        operation_plan=operation_plan,
    )


def _current_review_draft_version(
    draft_repository: SQLiteReviewDraftRepository,
    plan: object,
) -> str:
    task_id = _review_plan_target(plan, "review_draft")
    snapshot = draft_repository.get(task_id)
    return str(snapshot.version) if snapshot is not None else "missing"


def _run_review_draft_plan(
    draft_repository: SQLiteReviewDraftRepository,
    plan: object,
) -> dict[str, object]:
    task_id = _review_plan_target(plan, "review_draft")
    base_version = int(_review_plan_target(plan, "review_draft_base_version"))
    if plan.action == "review_drafts.delete":
        try:
            draft_repository.delete_if_version(task_id, base_version)
        except ReviewDraftConflictError as exc:
            current = exc.current
            raise OperationPlanVersionConflict(
                f"expected review draft version {base_version}, got {current.version if current else 'missing'}"
            ) from exc
        return {"task_id": task_id, "deleted": True}
    if plan.action == "review_drafts.restore":
        restore_version = int(_review_plan_target(plan, "review_draft_restore_version"))
        try:
            snapshot = draft_repository.restore(task_id, restore_version, base_version)
        except ReviewDraftConflictError as exc:
            raise OperationPlanVersionConflict("review draft version changed during restoration") from exc
        if snapshot is None:
            raise OperationPlanError("review draft version not found")
        return draft_response_data(snapshot)
    raise OperationPlanError("unsupported review draft operation action")


def _review_plan_target(plan: object, target_type: str) -> str:
    if not getattr(plan, "action", "").startswith("review_drafts."):
        raise OperationPlanError("unsupported review draft operation action")
    for target in getattr(plan, "targets", []):
        if target.type == target_type:
            return target.id
    raise OperationPlanError(f"review draft operation is missing {target_type}")


def draft_response_data(snapshot: ReviewDraftSnapshot) -> dict[str, object]:
    return {
        "task_id": snapshot.task_id,
        "version": snapshot.version,
        "state": snapshot.state,
        "updated_at": snapshot.updated_at.isoformat(),
    }
