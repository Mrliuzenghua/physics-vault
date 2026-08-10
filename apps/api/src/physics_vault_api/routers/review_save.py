from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.contracts import ObjectMapResponse
from ..repositories.review_drafts import ReviewDraftConflictError, ReviewDraftSnapshot, SQLiteReviewDraftRepository

from ..schemas.review_save import (
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
from ..services.review_save import ReviewSaveService


def build_review_save_router(
    service: ReviewSaveService | None = None,
    draft_repository: SQLiteReviewDraftRepository | None = None,
) -> APIRouter:
    if service is None:
        service = ReviewSaveService()
    if draft_repository is None:
        draft_repository = SQLiteReviewDraftRepository()

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
    async def list_review_draft_versions(task_id: str, limit: int = 20) -> ReviewDraftVersionListResponse:
        return ReviewDraftVersionListResponse(
            items=[draft_response(item) for item in draft_repository.list_versions(task_id, limit=limit)]
        )

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
