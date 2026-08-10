from __future__ import annotations

from pydantic import BaseModel


class ImageAssetItem(BaseModel):
    asset_id: str
    filename: str
    file_path: str
    paper_id: str | None = None
    question_id: str | None = None
    source_id: str | None = None
    role: str
    sort_order: int
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    description: str | None = None
    extracted_text: str | None = None
    image_type: str | None = None
    binding_confidence: float | None = None
    verified: bool
