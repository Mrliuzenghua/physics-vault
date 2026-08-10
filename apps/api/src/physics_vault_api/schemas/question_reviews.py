from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewActionRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = None
    reviewer: str | None = None


class ReviewActionResponse(BaseModel):
    question_id: str
    action: str
    status: str
    review_id: str


class ProposeFixRequest(BaseModel):
    new_stem_text: str = Field(min_length=1)
    fix_type: str = "full"
    summary: str | None = None
    reason: str | None = None
    ai_source: str | None = None


class ProposeFixResponse(BaseModel):
    review_id: str
    question_id: str
    status: str


class ReportIssueRequest(BaseModel):
    issue_type: str = "content"
    description: str | None = None
    reporter: str | None = None


class ReportIssueResponse(BaseModel):
    review_id: str
    question_id: str
    status: str


class ReviewQueueItem(BaseModel):
    review_id: str
    entity_type: str
    entity_id: str
    queue_type: str
    status: str
    priority: int
    reason: str | None = None
    payload_json: str | None = None
    created_at: str
    updated_at: str


class PendingFixItem(BaseModel):
    review_id: str
    question_id: str
    fix_type: str | None = None
    summary: str | None = None
    reason: str | None = None
    ai_source: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    status: str | None = None
    created_at: str


class RejectedQuestionItem(BaseModel):
    question_id: str
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    status: str
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    latest_reason: str | None = None
    latest_queue_type: str | None = None
    latest_at: str | None = None
    pending_fix_count: int = 0


class FixDetailResponse(BaseModel):
    review_id: str
    question_id: str
    queue_type: str
    status: str
    reason: str | None = None
    fix_type: str | None = None
    summary: str | None = None
    ai_source: str | None = None
    current_stem_text: str | None = None
    new_stem_text: str | None = None
    created_at: str


class DecideFixRequest(BaseModel):
    action: Literal["apply", "reject"]
    reviewer: str | None = None
    reason: str | None = None


class DecideFixResponse(BaseModel):
    review_id: str
    question_id: str
    action: str
    question_status: str
