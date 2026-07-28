"""Business-level service for AI-powered analysis and knowledge generation.

Wraps ``McpGatewayService`` so that callers (routers, other services)
never deal with MCP protocol details directly.  Includes a knowledge-point
generation cache backed by SQLite to avoid repeated MCP calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from mcp_contracts.src.models import (  # type: ignore[import-not-found]
    GenerateAnalysisInput,
    GenerateAnalysisOutput,
    GenerateKnowledgeInput,
    GenerateKnowledgeOutput,
    QuestionFigure,
    QuestionOption,
    StandardQuestion,
)

from ..repositories.knowledge_cache import KnowledgeCacheRepository
from ..schemas.ai_generation import (
    GenerateAnalysisRequest,
    GenerateAnalysisResponse,
    GenerateKnowledgeRequest,
    GenerateKnowledgeResponse,
    QuestionSummary,
)
from .mcp_gateway import AppError, McpGatewayService

logger = logging.getLogger(__name__)


class AiGenerationService:
    """Business facade over the MCP gateway for analysis & knowledge tasks.

    Responsibilities:
    - Translate business schemas → MCP models
    - Handle AI-disabled / offline scenarios gracefully
    - Cache knowledge-point generation results in SQLite
    """

    def __init__(
        self,
        gateway: McpGatewayService,
        cache_repo: KnowledgeCacheRepository | None = None,
    ) -> None:
        self._gateway = gateway
        self._cache = cache_repo or KnowledgeCacheRepository()

    # ── Cache helpers ─────────────────────────────────────────────

    @staticmethod
    def _compute_cache_key(
        knowledge_points: list[str],
        style: str,
        length: str,
    ) -> str:
        """Produce a stable, order-independent cache key.

        Knowledge points are sorted before hashing so that different
        orderings of the same set resolve to the same key.
        """
        canonical = sorted(k.strip() for k in knowledge_points if k.strip())
        payload = "|".join(canonical) + f"||{style}||{length}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _entry_from_cache_row(row: dict[str, Any]) -> dict[str, Any]:
        """Parse a SQLite row dict into the response-relevant fields."""
        outline = []
        raw_outline = row.get("outline_json", "[]")
        if raw_outline:
            try:
                outline = json.loads(raw_outline)
            except (json.JSONDecodeError, TypeError):
                outline = []
        return {
            "knowledge_key": row.get("cache_key", ""),
            "title": row.get("title", ""),
            "content": row.get("content", ""),
            "outline": outline if isinstance(outline, list) else [],
        }

    # ── Cache management (public) ─────────────────────────────────

    def clear_knowledge_cache(self) -> int:
        """Delete all knowledge-point cache entries. Returns deleted count."""
        try:
            return self._cache.clear_all()
        except FileNotFoundError:
            return 0
        except Exception:
            logger.exception("Failed to clear knowledge cache")
            return 0

    def delete_knowledge_cache_entry(self, cache_key: str) -> bool:
        """Delete a single cache entry by key. Returns True if deleted."""
        try:
            return self._cache.delete(cache_key)
        except FileNotFoundError:
            return False
        except Exception:
            logger.exception("Failed to delete cache entry %s", cache_key)
            return False

    # ── Analysis ─────────────────────────────────────────────────

    async def generate_analysis(
        self, request: GenerateAnalysisRequest
    ) -> GenerateAnalysisResponse:
        """Generate a detailed analysis (解析) for a single question."""

        status = self._gateway.status()
        if not status["enabled"] or status["mode"] == "disabled":
            return GenerateAnalysisResponse(
                question_id=request.question.question_id,
                analysis_text="",
                generated=False,
                warnings=["AI 服务已禁用，无法生成解析。请在 MCP 设置中启用 AI 后重试。"],
            )

        if not status["llm_available"]:
            return GenerateAnalysisResponse(
                question_id=request.question.question_id,
                analysis_text="",
                generated=False,
                warnings=[
                    "LLM 服务不可用（检查 PHYSICS_MCP_LLM_COMMAND 环境变量或 MCP 设置）。"
                ],
            )

        mcp_input = _to_generate_analysis_input(request)

        try:
            result: dict[str, Any] = await self._gateway.generate_analysis(mcp_input)
        except AppError as exc:
            logger.warning("Analysis generation failed: %s", exc.message)
            return GenerateAnalysisResponse(
                question_id=request.question.question_id,
                analysis_text="",
                generated=False,
                warnings=[f"生成失败: {exc.message}"],
            )
        except Exception as exc:
            logger.exception("Unexpected error during analysis generation")
            return GenerateAnalysisResponse(
                question_id=request.question.question_id,
                analysis_text="",
                generated=False,
                warnings=[f"生成异常: {exc}"],
            )

        # AI may return:
        # - plain text → wrap in analysis_text
        # - structured JSON dict → serialize whole dict so frontend can parse all fields
        raw_text = str(result.get("analysis_text") or result.get("text") or "")
        if not raw_text and isinstance(result, dict):
            # If the result itself is the structured output, serialize it
            structured_keys = {"question_type", "difficulty", "knowledge_point", "tags", "options", "answer", "analysis"}
            if any(k in result for k in structured_keys):
                import json as _json
                raw_text = _json.dumps(result, ensure_ascii=False)
            elif len(result) > 1:  # has more than just question_id
                import json as _json
                raw_text = _json.dumps(result, ensure_ascii=False)

        return GenerateAnalysisResponse(
            question_id=result.get("question_id", request.question.question_id),
            analysis_text=raw_text,
            analysis_structured=result.get("analysis_structured") or result.get("structured") or {},
            generated=bool(raw_text),
            warnings=[w.get("message", str(w)) for w in result.get("warnings", [])],
        )

    # ── Knowledge (with cache) ────────────────────────────────────

    async def generate_knowledge(
        self, request: GenerateKnowledgeRequest
    ) -> GenerateKnowledgeResponse:
        """Generate explanatory content for a knowledge-point topic.

        Cache logic:
        1. Compute cache key (order-independent hash of kps + style + length)
        2. If not force_regenerate: check cache → hit → return cached
        3. If cache miss or force_regenerate: call MCP
        4. On MCP success: write/update cache
        5. On MCP failure: do NOT corrupt existing cache; return error
        """

        status = self._gateway.status()
        if not status["enabled"] or status["mode"] == "disabled":
            return GenerateKnowledgeResponse(
                generated=False,
                from_cache=False,
                warnings=["AI 服务已禁用，无法生成知识点内容。请在 MCP 设置中启用 AI 后重试。"],
            )

        if not status["llm_available"]:
            return GenerateKnowledgeResponse(
                generated=False,
                from_cache=False,
                warnings=[
                    "LLM 服务不可用（检查 PHYSICS_MCP_LLM_COMMAND 环境变量或 MCP 设置）。"
                ],
            )

        cache_key = self._compute_cache_key(
            request.knowledge_points, request.style, request.length
        )

        # ── Cache lookup ──
        if not request.force_regenerate:
            try:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    logger.debug("Knowledge cache hit: %s", cache_key[:16])
                    data = self._entry_from_cache_row(cached)
                    return GenerateKnowledgeResponse(
                        knowledge_key=data["knowledge_key"],
                        title=data["title"],
                        content=data["content"],
                        outline=data["outline"],
                        generated=True,
                        from_cache=True,
                        warnings=[],
                    )
            except FileNotFoundError:
                pass  # DB not available → fall through to MCP
            except Exception:
                logger.warning("Cache lookup failed for key %s", cache_key[:16])

        # ── Call MCP ──
        mcp_input = GenerateKnowledgeInput(
            knowledge_points=list(request.knowledge_points),
            style=request.style,
            length=request.length,
            include_formula=request.include_formula,
            include_common_mistakes=request.include_common_mistakes,
        )

        try:
            result: dict[str, Any] = await self._gateway.generate_knowledge(mcp_input)
        except AppError as exc:
            logger.warning("Knowledge generation failed: %s", exc.message)
            return GenerateKnowledgeResponse(
                generated=False,
                from_cache=False,
                warnings=[f"生成失败: {exc.message}"],
            )
        except Exception as exc:
            logger.exception("Unexpected error during knowledge generation")
            return GenerateKnowledgeResponse(
                generated=False,
                from_cache=False,
                warnings=[f"生成异常: {exc}"],
            )

        # ── Write cache (only on success) ──
        try:
            self._cache.upsert({
                "cache_key": cache_key,
                "knowledge_points_json": json.dumps(
                    sorted(k.strip() for k in request.knowledge_points if k.strip()),
                    ensure_ascii=False,
                ),
                "style": request.style,
                "length": request.length,
                "title": str(result.get("title", "")),
                "content": str(result.get("content", "")),
                "outline_json": json.dumps(
                    list(result.get("outline", [])), ensure_ascii=False
                ),
            })
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("Failed to write knowledge cache for key %s", cache_key[:16])

        return GenerateKnowledgeResponse(
            knowledge_key=str(result.get("knowledge_key", "")),
            title=str(result.get("title", "")),
            content=str(result.get("content", "")),
            outline=list(result.get("outline", [])),
            generated=True,
            from_cache=False,
            warnings=[w.get("message", str(w)) for w in result.get("warnings", [])],
        )


# ── Internal helpers (model conversion) ────────────────────────────

def _to_generate_analysis_input(
    request: GenerateAnalysisRequest,
) -> GenerateAnalysisInput:
    """Convert the business request into the MCP-layer input model."""
    q = request.question
    sq = StandardQuestion(
        question_id=q.question_id,
        question_type=q.question_type,  # type: ignore[arg-type]
        title=q.title,
        options=[QuestionOption(**opt) for opt in q.options],
        answer=q.answer,
        analysis=q.analysis,
        sub_questions=[],
        figures=[QuestionFigure(**fig) for fig in q.figures],
        difficulty=q.difficulty,
        knowledge_point=q.knowledge_point,
        tags=list(q.tags),
        source=q.source,
        import_batch_id=q.import_batch_id,
    )
    return GenerateAnalysisInput(
        question=sq,
        style=request.style,
        include_extension=request.include_extension,
        allow_figure_refs=True,
    )
