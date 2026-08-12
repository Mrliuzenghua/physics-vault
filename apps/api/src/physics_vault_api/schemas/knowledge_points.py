from __future__ import annotations

from pydantic import BaseModel, Field

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from mcp_contracts.src.operation_plan import OperationPlan


class KnowledgePointItem(BaseModel):
    topic3_id: str
    topic3_name: str
    topic2_id: str
    topic2_name: str
    topic1_id: str
    topic1_name: str
    source_chapter: str | None = None
    status: str
    note: str | None = None


class QuestionKnowledgePointLink(BaseModel):
    rank: int
    topic1_id: str
    topic1_name: str
    topic2_id: str
    topic2_name: str
    topic3_id: str
    topic3_name: str
    source_chapter: str | None = None
    source: str | None = None
    confidence: float | None = None
    note: str | None = None


class QuestionKnowledgePointUpsert(BaseModel):
    topic3_id: str
    source: str = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    note: str | None = None


class QuestionKnowledgePointBatchItem(QuestionKnowledgePointUpsert):
    rank: int = Field(ge=1, le=3)


class QuestionKnowledgePointReplacePreviewRequest(BaseModel):
    """Preview a single-question replacement before durable confirmation."""

    model_config = {"extra": "forbid"}

    items: list[QuestionKnowledgePointBatchItem] = Field(..., min_length=1, max_length=3)
    reason: str = Field(..., min_length=1, max_length=300)


class QuestionKnowledgePointReplacePreviewResponse(BaseModel):
    question_id: str
    before_links: list[QuestionKnowledgePointLink] = Field(default_factory=list)
    replacement_items: list[QuestionKnowledgePointBatchItem] = Field(default_factory=list)
    changed: bool
    requires_confirmation: bool
    operation_plan: OperationPlan | None = None


class ConfirmQuestionKnowledgePointOperationRequest(BaseModel):
    """Confirmation cannot change the persisted replacement payload."""

    model_config = {"extra": "forbid"}

    operation_id: str = Field(..., min_length=1)


class QuestionKnowledgePointOperationResult(BaseModel):
    question_id: str
    links: list[QuestionKnowledgePointLink] = Field(default_factory=list)
    audit_batch_id: str | None = None


class QuestionKnowledgePointOperationExecutionResponse(BaseModel):
    operation_id: str
    status: str
    result: QuestionKnowledgePointOperationResult | None = None
    error: str | None = None
    idempotent: bool = False
