from __future__ import annotations

from pydantic import BaseModel


class EmbeddingStatusItem(BaseModel):
    model_name: str
    model_version: str | None = None
    vector_type: str
    owner_count: int
    last_updated_at: str | None = None
