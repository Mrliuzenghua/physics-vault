from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)


class SearchError(ValueError):
    """Raised when search parameters are invalid."""


class QuestionSearchService:
    """Business-logic layer for question search.

    Delegates data access to *QuestionSearchRepository* and handles
    parameter validation, search-mode routing, scoring, and model mapping.
    """

    def __init__(self, repository: QuestionSearchRepository | None = None) -> None:
        self._repo = repository or QuestionSearchRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, params: QuestionSearchParams) -> SearchResponse:
        """Execute a search and return a structured response envelope."""
        self._validate(params)

        search_mode = params.search_mode.value

        # hybrid / similar degrade to strict in the first version
        if search_mode in ("hybrid", "similar"):
            logger.info(
                "search_mode=%s requested – degrading to strict (v1 limitation).",
                search_mode,
            )
            search_mode = "strict"

        rows, total = self._repo.search_questions(
            search_mode=search_mode,
            query=params.query,
            year=params.year,
            module=params.module,
            question_type=params.question_type,
            difficulty=params.difficulty,
            status=params.status,
            topic1_id=params.topic1_id,
            topic2_id=params.topic2_id,
            topic3_id=params.topic3_id,
            topic2=params.topic2,
            topic3=params.topic3,
            region=params.region,
            exam_type=params.exam_type,
            has_media=params.has_media,
            image_count_min=params.image_count_min,
            is_mistake=params.is_mistake,
            limit=params.limit,
            offset=params.offset,
        )

        items = [self._row_to_item(row, search_mode, params.query) for row in rows]
        facets = self._build_facets_block()

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
        figures = (
            json.loads(row["image_filenames_json"])
            if isinstance(row.get("image_filenames_json"), str) and row["image_filenames_json"]
            else (row.get("image_filenames_json") if isinstance(row.get("image_filenames_json"), list) else [])
        )
        knowledge_points = row.get("knowledge_points", []) or []

        # Compute keyword match for scoring
        keyword_match = False
        if query and search_mode == "strict":
            q = query.lower()
            keyword_match = any(
                q in (str(row.get(f)) or "").lower()
                for f in ("canonical_title", "stem_text", "answer_text", "analysis_text")
            )

        # Resolve year from paper_year or explicit year filter
        resolved_year = row.get("paper_year")

        return QuestionItem(
            question_id=row["question_id"],
            question_type=row.get("question_type"),
            title=row.get("canonical_title"),
            answer=row.get("answer_text"),
            analysis=row.get("analysis_text"),
            options=options,
            figures=figures,
            difficulty=str(row.get("difficulty", "")) if row.get("difficulty") is not None else None,
            knowledge_point=row.get("topic3"),
            tags=self._build_tags(row),
            source=row.get("primary_paper_id"),
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
            similarity=None,
            keyword_match=keyword_match,
            search_mode=search_mode,
            score=1.0 if keyword_match else 0.0,
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

    @staticmethod
    def _build_tags(row: dict[str, Any]) -> list[str]:
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
