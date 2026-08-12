from __future__ import annotations

import json
import logging
import re
from pathlib import PureWindowsPath
from typing import Any

from ..repositories.question_search import QuestionSearchRepository
from ..schemas.question_search import (
    BatchQuestionFetchRequest,
    BatchQuestionFetchResponse,
    FacetBlock,
    FilterFacetsResponse,
    QuestionItem,
    QuestionSearchParams,
    SearchResponse,
)
from .semantic_retrieval import SemanticRetrievalService, SemanticSearchUnavailable

logger = logging.getLogger(__name__)


_SOURCE_REGIONS = (
    "北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
    "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门", "全国",
)
_SOURCE_EXAM_TYPES = ("高考", "学考", "选考")
_SOURCE_QUERY_ALIASES = {
    "深一模": (None, None, "深圳 第一次调研"),
    "深二模": (None, None, "深圳 第二次调研"),
}


def _has_source_alias(query: str | None) -> bool:
    compact = re.sub(r"\s+", "", str(query or ""))
    return any(alias in compact for alias in _SOURCE_QUERY_ALIASES)


def _extract_source_filters(query: str | None) -> tuple[str | None, str | None, str | None]:
    """Turn source-like queries into reliable structured filters.

    A query such as ``广东高考`` is not a request for semantically similar
    mechanics questions; it names a paper scope.  Strip recognised metadata
    from the free-text part so it can be applied as exact region/exam filters.
    """
    remaining = str(query or "").strip()
    if not remaining:
        return None, None, None

    compact = re.sub(r"\s+", "", remaining)
    for alias, expanded in _SOURCE_QUERY_ALIASES.items():
        if alias in compact:
            region, exam_type, source_terms = expanded
            suffix = compact.replace(alias, "", 1)
            return region, exam_type, f"{source_terms} {suffix}".strip()

    region = next((item for item in _SOURCE_REGIONS if item in remaining), None)
    exam_type = next((item for item in _SOURCE_EXAM_TYPES if item in remaining), None)
    if region:
        remaining = remaining.replace(region, " ")
    if exam_type:
        remaining = remaining.replace(exam_type, " ")
    remaining = re.sub(r"[·、,，/\\\\|_-]+", " ", remaining)
    remaining = " ".join(remaining.split())
    return region, exam_type, remaining or None


class SearchError(ValueError):
    """Raised when search parameters are invalid."""


class QuestionSearchService:
    """Business-logic layer for question search.

    Delegates data access to *QuestionSearchRepository* and handles
    parameter validation, search-mode routing, scoring, and model mapping.
    """

    def __init__(
        self,
        repository: QuestionSearchRepository | None = None,
        semantic_service: SemanticRetrievalService | None = None,
    ) -> None:
        self._repo = repository or QuestionSearchRepository()
        self._semantic = semantic_service or SemanticRetrievalService(self._repo)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, params: QuestionSearchParams, *, include_facets: bool = True) -> SearchResponse:
        """Execute a search and return a structured response envelope."""
        self._validate(params)

        search_mode = params.search_mode.value
        inferred_region, inferred_exam_type, remaining_query = _extract_source_filters(params.query)
        source_intent = bool(inferred_region or inferred_exam_type or _has_source_alias(params.query))
        effective_params = params.model_copy(update={
            "region": params.region or inferred_region,
            "exam_type": params.exam_type or inferred_exam_type,
            "query": remaining_query if source_intent else params.query,
        })

        if search_mode in ("hybrid", "similar") and effective_params.query and not source_intent:
            try:
                semantic = self._semantic.search(effective_params)
                items = [
                    self._row_to_item(row, search_mode, params.query)
                    for row in semantic.rows
                ]
                facets = self._build_facets_block() if include_facets else None
                return SearchResponse(
                    items=items,
                    total=semantic.total,
                    limit=params.limit,
                    offset=params.offset,
                    search_mode=search_mode,
                    facets=facets,
                )
            except SemanticSearchUnavailable as exc:
                logger.info("semantic search unavailable; falling back to strict: %s", exc)
            except Exception as exc:
                logger.warning("semantic search failed; falling back to strict: %s", exc)

        # hybrid / similar degrade to strict in the first version
        if search_mode in ("hybrid", "similar"):
            logger.info(
                "search_mode=%s requested – degrading to strict (v1 limitation).",
                search_mode,
            )
            search_mode = "strict"

        rows, total = self._repo.search_questions(
            search_mode=search_mode,
            query=effective_params.query,
            year=effective_params.year,
            module=effective_params.module,
            question_type=effective_params.question_type,
            difficulty=effective_params.difficulty,
            status=effective_params.status,
            topic1_id=effective_params.topic1_id,
            topic2_id=effective_params.topic2_id,
            topic3_id=effective_params.topic3_id,
            topic2=effective_params.topic2,
            topic3=effective_params.topic3,
            region=effective_params.region,
            exam_type=effective_params.exam_type,
            has_media=effective_params.has_media,
            image_count_min=effective_params.image_count_min,
            is_mistake=effective_params.is_mistake,
            limit=effective_params.limit,
            offset=effective_params.offset,
        )

        items = [self._row_to_item(row, search_mode, params.query) for row in rows]
        facets = self._build_facets_block() if include_facets else None

        return SearchResponse(
            items=items,
            total=total,
            limit=params.limit,
            offset=params.offset,
            search_mode=params.search_mode.value,
            facets=facets,
        )

    def get_facets(self) -> FilterFacetsResponse:
        """Return distinct filter values for all facet dimensions."""
        data = self._repo.get_facets()
        return FilterFacetsResponse(**data)

    def get_by_ids(self, request: BatchQuestionFetchRequest) -> BatchQuestionFetchResponse:
        rows = self._repo.get_questions_by_ids(request.question_ids)
        items = [self._row_to_item(row, "browse", None) for row in rows]
        found_ids = {item.question_id for item in items}
        missing_ids = [qid for qid in request.question_ids if qid not in found_ids]
        return BatchQuestionFetchResponse(items=items, missing_ids=missing_ids)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(params: QuestionSearchParams) -> None:
        mode = params.search_mode.value
        if mode in ("strict", "hybrid", "similar") and not params.query:
            raise SearchError("query is required for strict, hybrid, or similar search mode")

    # ------------------------------------------------------------------
    # Row → Item mapping
    # ------------------------------------------------------------------

    def _row_to_item(
        self,
        row: dict[str, Any],
        search_mode: str,
        query: str | None,
    ) -> QuestionItem:
        options = self._parse_options(row.get("options_json"))
        figures = self._parse_figures(
            row.get("figures_json"),
            row.get("image_asset_ids_json"),
            row.get("image_filenames_json"),
        )
        knowledge_points = row.get("knowledge_points", []) or []

        # Compute keyword match for scoring
        keyword_match = bool(row.get("keyword_match", False))
        if query and search_mode == "strict":
            q = query.lower()
            searchable_values = [
                row.get(field)
                for field in (
                    "canonical_title",
                    "stem_text",
                    "answer_text",
                    "analysis_text",
                    "tags_json",
                    "source_text",
                    "source_label",
                    "module",
                    "topic2",
                    "topic3",
                )
            ]
            searchable_values.extend(
                point.get("topic3_name") or point.get("topic2_name") or point.get("topic1_name")
                for point in knowledge_points
                if isinstance(point, dict)
            )
            keyword_match = any(q in str(value or "").lower() for value in searchable_values)

        raw_search_score = row.get("search_score")
        try:
            search_score = float(raw_search_score) if raw_search_score is not None else None
        except (TypeError, ValueError):
            search_score = None

        raw_similarity = row.get("similarity")
        try:
            similarity = float(raw_similarity) if raw_similarity is not None else None
        except (TypeError, ValueError):
            similarity = None

        # Resolve year from paper_year or explicit year filter
        resolved_year = row.get("paper_year")

        return QuestionItem(
            question_id=row["question_id"],
            question_type=row.get("question_type"),
            title=row.get("title_text") or row.get("canonical_title"),
            answer=row.get("answer_text"),
            analysis=row.get("analysis_text"),
            options=options,
            figures=figures,
            difficulty=str(row.get("difficulty", "")) if row.get("difficulty") is not None else None,
            knowledge_point=row.get("topic3"),
            tags=self._build_tags(row),
            source=self._resolve_display_source(row),
            year=resolved_year,
            status=row.get("status"),
            is_mistake=bool(row.get("is_mistake", False)),
            mistake_marked_at=row.get("mistake_marked_at"),
            knowledge_points=knowledge_points,
            # Legacy compatibility
            canonical_title=row.get("canonical_title"),
            module=row.get("module"),
            topic2=row.get("topic2"),
            topic3=row.get("topic3"),
            primary_paper_id=row.get("primary_paper_id"),
            primary_question_no=row.get("primary_question_no"),
            vault_markdown_path=row.get("vault_markdown_path"),
            has_media=bool(row.get("has_media", False)),
            image_count=row.get("image_count", 0),
            # Scoring
            similarity=similarity,
            keyword_match=keyword_match,
            search_mode=search_mode,
            score=search_score if search_score is not None else (1.0 if keyword_match else 0.0),
            method_match=row.get("method_match"),
        )

    @staticmethod
    def _parse_options(raw: str | None) -> list[dict[str, Any]]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @classmethod
    def _resolve_display_source(cls, row: dict[str, Any]) -> str | None:
        for key in ("source_label", "paper_name", "source_text", "source", "primary_paper_id"):
            label = cls._normalize_source_label(row.get(key))
            if label:
                return label
        return None

    @staticmethod
    def _normalize_source_label(raw: Any) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text or text.lower() in {"none", "null"}:
            return None
        if text.startswith("batch_"):
            return None

        label = PureWindowsPath(text).name or text
        lower_label = label.lower()
        for suffix in (".docx", ".doc", ".pdf", ".md", ".txt", ".json", ".png", ".jpg", ".jpeg", ".webp"):
            if lower_label.endswith(suffix):
                label = label[: -len(suffix)]
                break
        return label.strip() or None

    @staticmethod
    def _parse_json_list(raw: Any) -> list[Any]:
        if isinstance(raw, list):
            return raw
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @classmethod
    def _parse_figures(
        cls,
        figures_raw: Any,
        asset_ids_raw: Any,
        filenames_raw: Any,
    ) -> list[dict[str, Any]]:
        figures = cls._parse_json_list(figures_raw)
        if figures and all(isinstance(item, dict) for item in figures):
            return figures

        asset_ids = [str(item) for item in cls._parse_json_list(asset_ids_raw) if item]
        filenames = [str(item) for item in cls._parse_json_list(filenames_raw) if item]
        result: list[dict[str, Any]] = []
        for index, filename in enumerate(filenames):
            fig_uuid = asset_ids[index] if index < len(asset_ids) else filename
            result.append({"fig_uuid": fig_uuid, "local_path": filename})
        return result

    @staticmethod
    def _build_tags(row: dict[str, Any]) -> list[str]:
        raw_tags = row.get("tags_json")
        if raw_tags:
            try:
                parsed_tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
            except (TypeError, json.JSONDecodeError):
                parsed_tags = []
            if isinstance(parsed_tags, list):
                curated_tags = list(
                    dict.fromkeys(
                        str(tag).strip() for tag in parsed_tags if str(tag).strip()
                    )
                )
                if curated_tags:
                    return curated_tags

        # Backward-compatible fallback for older records that predate stored
        # teaching tags.  Once a record has curated tags, return those rather
        # than re-synthesising knowledge-point and difficulty labels.
        tags: list[str] = []
        if row.get("module"):
            tags.append(row["module"])
        if row.get("topic2"):
            tags.append(row["topic2"])
        if row.get("topic3"):
            tags.append(row["topic3"])
        if row.get("difficulty"):
            tags.append(f"难度{row['difficulty']}")
        return tags

    # ------------------------------------------------------------------
    # Facets block (inlined inside search response)
    # ------------------------------------------------------------------

    def _build_facets_block(self) -> FacetBlock:
        data = self._repo.get_facets()
        return FacetBlock(**data)
