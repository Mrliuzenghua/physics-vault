from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .ai_assistant import AiAssistantMessage, AiAssistantQuestionContext


class AgentConfig(BaseModel):
    claude_code_path: str = ""
    enabled: bool = False
    timeout_seconds: int = Field(default=300, ge=10, le=600)


class AgentConfigResponse(BaseModel):
    config: AgentConfig
    available: bool = False
    message: str = ""


class AgentConfigUpdateRequest(BaseModel):
    claude_code_path: str = ""
    enabled: bool = True
    timeout_seconds: int = Field(default=300, ge=10, le=600)


class AgentTestResponse(BaseModel):
    ok: bool
    message: str
    version: str | None = None


class ReviewLatexCleanupRequest(BaseModel):
    task_id: str | None = Field(default=None, max_length=120)
    user_text: str | None = Field(default=None, max_length=500)
    dry_run: bool = False


class ReviewLatexCleanupResponse(BaseModel):
    ok: bool
    task_id: str | None = None
    dry_run: bool = False
    fast_path: bool = True
    changed_questions: int = 0
    replacement_count: int = 0
    elapsed_ms: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    message: str = ""


class AgentAction(BaseModel):
    action_id: str
    type: Literal["add_to_basket", "create_paper_draft", "open_questions"]
    label: str
    question_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True


class AgentTraceStep(BaseModel):
    title: str
    detail: str
    status: Literal["done", "warning", "error"] = "done"


class AgentStreamEvent(BaseModel):
    type: Literal["trace", "terminal", "warning", "error", "response"]
    message: str | None = None
    step: AgentTraceStep | None = None
    response: "QuestionPickerAgentResponse | None" = None


class QuestionPickerAgentRequest(BaseModel):
    messages: list[AiAssistantMessage] = Field(..., min_length=1, max_length=30)
    query: str | None = None
    context_limit: int = Field(default=12, ge=1, le=30)
    context_question_ids: list[str] = Field(default_factory=list, max_length=50)
    session_id: str | None = Field(default=None, max_length=80)
    resume_session: bool = False


class QuestionPickerAgentResponse(BaseModel):
    reply: str
    agent_used: bool = False
    agent_name: str = "rule-based"
    session_id: str | None = None
    query_used: str = ""
    selected_questions: list[AiAssistantQuestionContext] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
    raw_agent_text: str | None = None


AgentStreamEvent.model_rebuild()
