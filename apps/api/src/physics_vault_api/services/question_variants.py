"""Business-level service for question variant generation.

Wraps ``McpGatewayService`` so that callers (routers, other services)
never deal with MCP protocol details directly.
"""

from __future__ import annotations

import logging
from typing import Any

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from mcp_contracts.src.models import (  # type: ignore[import-not-found]
    GenerateQuestionVariantsInput,
    GenerateQuestionVariantsOutput,
    VariantSourceQuestion,
)

from ..schemas.question_variants import (
    GenerateQuestionVariantsRequest,
    GenerateQuestionVariantsResponse,
    GeneratedVariantQuestion,
)
from .mcp_gateway import AppError, McpGatewayService

logger = logging.getLogger(__name__)


class QuestionVariantService:
    """Business facade over the MCP gateway for variant question generation.

    Responsibilities:
    - Validate input and enforce generation limits
    - Translate business schemas → MCP models
    - Handle AI-disabled / offline scenarios gracefully
    - Convert MCP output back to business response format
    """

    def __init__(self, gateway: McpGatewayService) -> None:
        self._gateway = gateway

    async def generate_variants(
        self, request: GenerateQuestionVariantsRequest
    ) -> GenerateQuestionVariantsResponse:
        """Generate variant questions from a source question."""

        # ── Availability checks ──
        status = self._gateway.status()
        if not status["enabled"] or status["mode"] == "disabled":
            return GenerateQuestionVariantsResponse(
                variants=[],
                generated=False,
                warnings=["AI 服务已禁用，无法生成变式题。请在 MCP 设置中启用 AI 后重试。"],
            )

        if not status["llm_available"]:
            return GenerateQuestionVariantsResponse(
                variants=[],
                generated=False,
                warnings=[
                    "LLM 服务不可用（检查 PHYSICS_MCP_LLM_COMMAND 环境变量或 MCP 设置）。"
                ],
            )

        # ── Build MCP input ──
        sq = request.source_question
        mcp_input = GenerateQuestionVariantsInput(
            source_question=VariantSourceQuestion(
                question_id=sq.question_id,
                question_type=sq.question_type,
                title=sq.title,
                options=[dict(o) for o in sq.options],
                answer=sq.answer,
                analysis=sq.analysis,
                difficulty=sq.difficulty,
                knowledge_point=sq.knowledge_point,
                tags=list(sq.tags),
                source=sq.source,
            ),
            variant_mode=request.variant_mode,  # type: ignore[arg-type]
            count=request.count,
            instructions=request.instructions,
            target_difficulty=request.target_difficulty,
            keep_knowledge_points=request.keep_knowledge_points,
        )

        # ── Call MCP ──
        try:
            result: dict[str, Any] = await self._gateway.generate_question_variants(mcp_input)
        except AppError as exc:
            logger.warning("Variant generation failed: %s", exc.message)
            return GenerateQuestionVariantsResponse(
                variants=[],
                generated=False,
                warnings=[f"变式题生成失败: {exc.message}"],
            )
        except Exception as exc:
            logger.exception("Unexpected error during variant generation")
            return GenerateQuestionVariantsResponse(
                variants=[],
                generated=False,
                warnings=[f"变式题生成异常: {exc}"],
            )

        # ── Convert to business response ──
        variants = [
            GeneratedVariantQuestion(
                question_type=str(v.get("question_type", "calculation")),
                title=str(v.get("title", "")),
                options=[dict(o) for o in v.get("options", [])],
                answer=str(v.get("answer", "")),
                analysis=str(v.get("analysis", "")),
                difficulty=v.get("difficulty"),
                knowledge_point=v.get("knowledge_point"),
                tags=list(v.get("tags", [])),
                source=v.get("source"),
                derived_from_question_id=v.get("derived_from_question_id"),
                variant_mode=v.get("variant_mode"),
                variant_note=v.get("variant_note"),
            )
            for v in result.get("variants", [])
        ]

        warnings = [w.get("message", str(w)) for w in result.get("warnings", [])]

        if len(variants) == 0 and result.get("generated", True):
            warnings.append("MCP 返回了空的变式题列表")

        return GenerateQuestionVariantsResponse(
            variants=variants,
            generated=len(variants) > 0,
            warnings=warnings,
        )
