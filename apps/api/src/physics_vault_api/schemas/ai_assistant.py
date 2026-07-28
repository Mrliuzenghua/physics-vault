from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AiAssistantMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class AiAssistantChatRequest(BaseModel):
    messages: list[AiAssistantMessage] = Field(..., min_length=1, max_length=30)
    query: str | None = None
    context_limit: int = Field(default=8, ge=1, le=20)
    temperature: float = Field(default=0.35, ge=0, le=1.2)


class AiAssistantQuestionContext(BaseModel):
    question_id: str
    title: str = ""
    question_type: str | None = None
    difficulty: str | None = None
    knowledge_point: str | None = None
    source: str | None = None
    answer: str | None = None
    analysis: str | None = None
    tags: list[str] = Field(default_factory=list)


class CompositionSuggestion(BaseModel):
    title: str
    rationale: str
    question_ids: list[str] = Field(default_factory=list)
    estimated_score: int = 0
    difficulty_mix: dict[str, int] = Field(default_factory=dict)


class AiAssistantChatResponse(BaseModel):
    reply: str
    model: str = "rule-based"
    ai_used: bool = False
    query_used: str = ""
    context_questions: list[AiAssistantQuestionContext] = Field(default_factory=list)
    composition_suggestions: list[CompositionSuggestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] | None = None

