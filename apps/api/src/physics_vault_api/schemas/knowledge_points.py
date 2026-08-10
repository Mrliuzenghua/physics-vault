from __future__ import annotations

from pydantic import BaseModel, Field


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
