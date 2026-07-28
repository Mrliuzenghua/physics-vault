"""Business-facing schemas for question variant generation.

These models define the public API contract for generating variant questions
from an existing source question, using the MCP LLM pipeline.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VariantMode = Literal[
    "change_condition",
    "change_question",
    "change_numbers",
    "same_model_new_context",
    "difficulty_up",
    "difficulty_down",
]

MAX_VARIANT_COUNT = 5


class SourceQuestionPayload(BaseModel):
    """Minimal source question representation needed for variant generation."""
    question_id: str = Field(..., min_length=1, description="原题 ID")
    question_type: str = Field(default="calculation", description="题型：single_choice / multi_choice / fill / experiment / calculation")
    title: str = Field(..., min_length=1, description="题干的完整文本")
    options: list[dict[str, Any]] = Field(default_factory=list, description="选择题选项（非选择题留空）")
    answer: str = Field(default="", description="原题答案")
    analysis: str = Field(default="", description="原题解析")
    difficulty: int | None = Field(default=None, ge=1, le=5, description="原题难度 1-5")
    knowledge_point: str | None = Field(default=None, description="原题知识点")
    tags: list[str] = Field(default_factory=list, description="原题标签")
    source: str | None = Field(default=None, description="原题来源")


class GenerateQuestionVariantsRequest(BaseModel):
    """Request to generate variant questions from a source question."""
    source_question: SourceQuestionPayload = Field(..., description="原题结构化数据")
    variant_mode: VariantMode = Field(..., description="变式方式")
    count: int = Field(
        default=1,
        ge=1,
        le=MAX_VARIANT_COUNT,
        description=f"生成数量，最多 {MAX_VARIANT_COUNT} 道",
    )
    instructions: str | None = Field(
        default=None,
        description="额外的变式要求说明，用于进一步约束生成方向",
    )
    target_difficulty: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="目标难度，用于 difficulty_up/down 模式",
    )
    keep_knowledge_points: bool = Field(
        default=True,
        description="是否保持原知识点不变",
    )


class GeneratedVariantQuestion(BaseModel):
    """A single generated variant question with full structured data."""
    question_type: str = Field(default="calculation")
    title: str = Field(default="")
    options: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = Field(default="")
    analysis: str = Field(default="")
    difficulty: int | None = Field(default=None)
    knowledge_point: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    source: str | None = Field(default=None)
    derived_from_question_id: str | None = Field(default=None, description="来源原题 ID")
    variant_mode: str | None = Field(default=None, description="使用的变式模式")
    variant_note: str | None = Field(default=None, description="变式说明")


class GenerateQuestionVariantsResponse(BaseModel):
    """Response containing generated variant questions."""
    variants: list[GeneratedVariantQuestion] = Field(
        default_factory=list, description="生成的变式题列表"
    )
    generated: bool = Field(default=True, description="是否成功生成")
    warnings: list[str] = Field(default_factory=list, description="生成过程中的警告信息")
