from __future__ import annotations

from pydantic import BaseModel


class ProcessingRunItem(BaseModel):
    """A persisted record for a legacy processing pipeline execution."""

    run_id: str
    pipeline_name: str
    pipeline_version: str
    paper_id: str | None = None
    question_id: str | None = None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    operator: str | None = None
    summary_json: str | None = None
