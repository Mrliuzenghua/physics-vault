"""Batch analysis generation with per-question isolation."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..repositories.question_search import QuestionSearchRepository
from ..repositories.question_write import QuestionWriteRepository
from ..schemas.ai_generation import GenerateAnalysisRequest, QuestionSummary
from ..schemas.analysis_batch import (
    BatchAnalysisItemResult,
    BatchGenerateAnalysisRequest,
    BatchGenerateAnalysisResponse,
)
from .ai_generation import AiGenerationService
from .workflow_concurrency import gather_limited

logger = logging.getLogger(__name__)

DEFAULT_ANALYSIS_CONCURRENCY = 3


class AnalysisBatchService:
    """Batch orchestrator for analysis generation.

    The service keeps every question isolated: one model failure returns one
    failed item and does not cancel the rest of the batch.
    """

    def __init__(
        self,
        ai_service: AiGenerationService,
        search_repo: QuestionSearchRepository | None = None,
        write_repo: QuestionWriteRepository | None = None,
        concurrency: int = DEFAULT_ANALYSIS_CONCURRENCY,
    ) -> None:
        self._ai = ai_service
        self._search = search_repo or QuestionSearchRepository()
        self._write = write_repo or QuestionWriteRepository()
        self._concurrency = max(1, concurrency)

    async def generate_batch(
        self, request: BatchGenerateAnalysisRequest
    ) -> BatchGenerateAnalysisResponse:
        """Process a batch of questions with limited concurrency."""

        async def process_guarded(question_id: str) -> BatchAnalysisItemResult:
            try:
                return await self._process_one(question_id, request)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error processing %s", question_id)
                return BatchAnalysisItemResult(
                    question_id=question_id,
                    status="failed",
                    message=f"处理异常: {exc}",
                    saved_to_db=False,
                )

        results = await gather_limited(request.question_ids, self._concurrency, process_guarded)

        return BatchGenerateAnalysisResponse(
            total=len(request.question_ids),
            success_count=sum(1 for item in results if item.status == "success"),
            skipped_count=sum(1 for item in results if item.status == "skipped"),
            failed_count=sum(1 for item in results if item.status == "failed"),
            results=results,
        )

    async def _process_one(
        self,
        question_id: str,
        batch_request: BatchGenerateAnalysisRequest,
    ) -> BatchAnalysisItemResult:
        question = self._fetch_question(question_id)
        if question is None:
            return BatchAnalysisItemResult(
                question_id=question_id,
                status="failed",
                message="题目不存在或无法读取",
                saved_to_db=False,
            )

        existing_analysis = str(question.get("analysis_text", "") or question.get("analysis", "") or "").strip()
        if existing_analysis and not batch_request.force_regenerate:
            return BatchAnalysisItemResult(
                question_id=question_id,
                status="skipped",
                message="已有解析，已跳过",
                saved_to_db=False,
            )

        summary = QuestionSummary(
            question_id=question_id,
            question_type=str(question.get("question_type", "calculation")),
            title=str(question.get("canonical_title", "") or question.get("title", "")),
            options=self._safe_json_list(question.get("options_json")) or [],
            answer=str(question.get("answer_text", "") or ""),
            analysis=existing_analysis,
            difficulty=self._safe_int(question.get("difficulty")),
            knowledge_point=str(question.get("topic3", "") or ""),
            tags=self._safe_tags(question.get("tags", [])),
            source=str(question.get("primary_paper_id", "") or ""),
        )

        response = await self._ai.generate_analysis(
            GenerateAnalysisRequest(
                question=summary,
                style=batch_request.style,
                include_extension=batch_request.include_extension,
                force_regenerate=batch_request.force_regenerate,
            )
        )

        if not response.generated:
            return BatchAnalysisItemResult(
                question_id=question_id,
                status="failed",
                message="; ".join(response.warnings) if response.warnings else "生成失败",
                saved_to_db=False,
            )

        saved = self._save_analysis(question_id, response.analysis_text)

        return BatchAnalysisItemResult(
            question_id=question_id,
            status="success",
            message="解析生成成功" + ("，已入库" if saved else "，入库失败"),
            saved_to_db=saved,
        )

    def _fetch_question(self, question_id: str) -> dict[str, Any] | None:
        """Fetch one question row from the repository."""
        rows, _ = self._search.search_questions(limit=200, offset=0)
        for row in rows:
            if row["question_id"] == question_id:
                return row
        return None

    def _save_analysis(self, question_id: str, analysis_text: str) -> bool:
        """Persist the analysis text back to the question_text_index table."""
        try:
            self._write.update_analysis(question_id, analysis_text)
            return True
        except Exception:
            logger.exception("Failed to save analysis for %s", question_id)
            return False

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_json_list(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    @staticmethod
    def _safe_tags(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(tag) for tag in raw if tag]
        return []
