from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas.question_search import (
    BatchQuestionFetchRequest,
    BatchQuestionFetchResponse,
    FilterFacetsResponse,
    QuestionSearchParams,
    SearchMode,
    SearchResponse,
)
from ..services.question_search import QuestionSearchService, SearchError


def build_question_search_router(
    service: QuestionSearchService | None = None,
) -> APIRouter:
    """Create a router exposing the question-search API surface.

    Routes are mounted at root level (no ``/api`` prefix) to stay
    compatible with the legacy frontend ``BrowsePage``.
    """
    if service is None:
        service = QuestionSearchService()

    router = APIRouter(tags=["question-search"])

    # ------------------------------------------------------------------
    # GET /search/questions
    # ------------------------------------------------------------------

    @router.get(
        "/search/questions",
        response_model=SearchResponse,
        summary="统一题目检索",
        description=(
            "统一题目检索入口。"
            "browse 用于纯筛选浏览；"
            "strict 用于按关键词和考点精确找题；"
            "hybrid / similar 当前退化为 strict。"
        ),
    )
    async def search_questions(  # noqa: PLR0913
        search_mode: SearchMode = Query(
            default=SearchMode.browse,
            description="检索模式：browse / strict / hybrid / similar",
        ),
        query: str | None = Query(
            default=None,
            description="查询关键词（strict / hybrid / similar 模式必填）",
        ),
        year: int | None = Query(default=None, description="年份筛选"),
        module: str | None = Query(default=None, description="模块筛选"),
        question_type: str | None = Query(default=None, description="题型筛选"),
        difficulty: str | None = Query(default=None, description="难度筛选"),
        status: str | None = Query(default=None, description="状态筛选"),
        topic1_id: str | None = Query(default=None, description="一级知识点 ID"),
        topic2_id: str | None = Query(default=None, description="二级知识点 ID"),
        topic3_id: str | None = Query(default=None, description="三级知识点 ID"),
        # Legacy-compatible parameters
        topic2: str | None = Query(default=None, description="二级考点名称"),
        topic3: str | None = Query(default=None, description="三级考点名称"),
        region: str | None = Query(default=None, description="地区筛选"),
        exam_type: str | None = Query(default=None, description="考试类型筛选"),
        has_media: bool | None = Query(default=None, description="是否有图片"),
        image_count_min: int = Query(default=0, ge=0, description="最少图片数"),
        is_mistake: bool | None = Query(default=None, description="错题筛选：true=仅错题, false=非错题, 不传=全部"),
        limit: int = Query(default=20, ge=1, le=200, description="返回条数"),
        offset: int = Query(default=0, ge=0, description="分页偏移"),
    ) -> SearchResponse:
        try:
            params = QuestionSearchParams(
                search_mode=search_mode,
                query=query,
                year=year,
                module=module,
                question_type=question_type,
                difficulty=difficulty,
                status=status,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                topic2=topic2,
                topic3=topic3,
                region=region,
                exam_type=exam_type,
                has_media=has_media,
                image_count_min=image_count_min,
                is_mistake=is_mistake,
                limit=limit,
                offset=offset,
            )
            return service.search(params)
        except SearchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "搜索服务暂时不可用", "detail": str(exc)},
            ) from exc

    # ------------------------------------------------------------------
    # GET /filters/facets
    # ------------------------------------------------------------------

    @router.get(
        "/filters/facets",
        response_model=FilterFacetsResponse,
        summary="筛选项聚合数据",
        description="返回前端筛选栏需要的所有可选项（年份、地区、模块、题型、难度、状态等）。",
    )
    async def get_facets() -> FilterFacetsResponse:
        try:
            return service.get_facets()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "筛选项加载失败", "detail": str(exc)},
            ) from exc

    @router.post(
        "/api/questions/batch-get",
        response_model=BatchQuestionFetchResponse,
        summary="按 ID 批量读取题目",
    )
    async def batch_get_questions(
        request: BatchQuestionFetchRequest,
    ) -> BatchQuestionFetchResponse:
        try:
            return service.get_by_ids(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "批量加载题目失败", "detail": str(exc)},
            ) from exc

    return router
