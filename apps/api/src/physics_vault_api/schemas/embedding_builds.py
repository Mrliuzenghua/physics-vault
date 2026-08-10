from __future__ import annotations

import os

from pydantic import BaseModel, Field


class EmbeddingBuildRequest(BaseModel):
    provider: str = Field(default_factory=lambda: os.getenv("PHYSICS_VAULT_EMBEDDING_PROVIDER", "openai"))
    model: str = Field(default_factory=lambda: os.getenv("PHYSICS_VAULT_EMBEDDING_MODEL", "text-embedding-3-small"))
    vector_type: str = Field(default_factory=lambda: os.getenv("PHYSICS_VAULT_EMBEDDING_VECTOR_TYPE", "semantic_search"))
    model_version: str = ""
    base_url: str | None = None
    dimensions: int | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)
    question_ids: list[str] = Field(default_factory=list)
    since_question_id: str | None = None
    max_tokens: int = Field(default=8000, ge=128, le=8192)
    batch_size: int = Field(default=20, ge=1, le=100)
    concurrency: int = Field(
        default_factory=lambda: int(os.getenv("PHYSICS_VAULT_EMBEDDING_CONCURRENCY", "1")),
        ge=1,
        le=16,
    )
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("PHYSICS_VAULT_EMBEDDING_MAX_RETRIES", "8")),
        ge=0,
        le=12,
    )
    force: bool = False
    dry_run: bool = False


class EmbeddingBuildResponse(BaseModel):
    run_id: str
    provider: str
    model_name: str
    vector_type: str
    processed_count: int
    embedded_count: int
    skipped_count: int
    failed_count: int
    dry_run: bool
