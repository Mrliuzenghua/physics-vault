"""Business-facing schemas for AI generation endpoints.

These differ from ``mcp_api.py`` which models the raw MCP protocol layer.
The schemas here are what the frontend / other services use to request
AI-powered analysis and knowledge-point content generation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Shared sub-models ───────────────────────────────────────────────

class QuestionSummary(BaseModel):
    """Minimal question representation needed by the generation service."""
    question_id: str = Field(..., min_length=1)
    question_type: str = Field(default="calculation")
    title: str = Field(default="")
    options: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = Field(default="")
    analysis: str = Field(default="")
    sub_questions: list[dict[str, Any]] = Field(default_factory=list)
    figures: list[dict[str, Any]] = Field(default_factory=list)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    knowledge_point: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    import_batch_id: str | None = None


# ── Analysis generation ─────────────────────────────────────────────

class GenerateAnalysisRequest(BaseModel):
    question: QuestionSummary
    style: Literal["classroom_brief", "self_study_full", "exam_standard"] = "classroom_brief"
    include_extension: bool = True
    force_regenerate: bool = Field(
        default=False,
        description="When True, re-generates even if analysis already exists.",
    )


class GenerateAnalysisResponse(BaseModel):
    question_id: str
    analysis_text: str = ""
    analysis_structured: dict[str, str] = Field(default_factory=dict)
    generated: bool = Field(default=True)
    warnings: list[str] = Field(default_factory=list)


# ── Knowledge-point generation ──────────────────────────────────────

class GenerateKnowledgeRequest(BaseModel):
    knowledge_points: list[str] = Field(..., min_length=1)
    style: str = Field(default="teacher_handout")
    length: Literal["short", "medium", "long"] = "medium"
    include_formula: bool = True
    include_common_mistakes: bool = True
    force_regenerate: bool = Field(
        default=False,
        description="设为 True 时跳过缓存，强制重新调用 AI 生成并覆盖缓存。",
    )
    context_questions: list[QuestionSummary] = Field(
        default_factory=list,
        description="Optional questions that demonstrate this knowledge point.",
    )


class GenerateKnowledgeResponse(BaseModel):
    knowledge_key: str = ""
    title: str = ""
    content: str = ""
    outline: list[str] = Field(default_factory=list)
    generated: bool = Field(default=True)
    from_cache: bool = Field(
        default=False,
        description="True 表示本次响应来自缓存，未重新调用 AI。",
    )
    warnings: list[str] = Field(default_factory=list)
