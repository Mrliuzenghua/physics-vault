from __future__ import annotations

from pydantic import BaseModel, Field


class QuestionDetail(BaseModel):
    question_id: str
    canonical_title: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    difficulty: str | None = None
    question_type: str | None = Field(default=None, alias="type")
    status: str
    has_media: bool
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    source: str | None = None
    knowledge_points: list[dict] = Field(default_factory=list)
    content_hash: str | None = None
    schema_version: str
    title_text: str | None = None
    stem_text: str | None = None
    stem_clean_text: str | None = None
    source_id: str | None = None
    image_asset_ids: list[str] = Field(default_factory=list)
    image_filenames: list[str] = Field(default_factory=list)
    image_count: int = 0
    answer_text: str | None = None
    analysis_text: str | None = None
    tips_text: str | None = None
    options_json: str | None = None
    figures: list[dict] = Field(default_factory=list)
    created_at: str
    updated_at: str


class QuestionAsset(BaseModel):
    link_id: str
    asset_id: str
    role: str
    sort_order: int
    placeholder_key: str | None = None
    is_primary: bool
    is_verified: bool
    filename: str
    file_path: str
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    description: str | None = None
    binding_confidence: float | None = None
    verified: bool
