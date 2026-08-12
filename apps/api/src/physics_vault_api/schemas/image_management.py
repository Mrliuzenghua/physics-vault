"""Schemas for question image management."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QuestionImageDetail(BaseModel):
    """Full info for one question image binding."""
    link_id: str
    asset_id: str
    filename: str
    file_path: str
    role: str = "stem"
    sort_order: int = 0
    placeholder_key: str | None = None
    display_scale: float = Field(default=60, ge=25, le=100)
    is_primary: bool = False
    is_verified: bool = False
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    description: str | None = None


class ImageListResponse(BaseModel):
    question_id: str
    images: list[QuestionImageDetail] = Field(default_factory=list)
    stem_text: str = ""


class AddImageRequest(BaseModel):
    asset_id: str
    role: str = "stem"
    sort_order: int | None = None
    placeholder_key: str | None = None
    is_primary: bool = False


class AddCachedImageRequest(BaseModel):
    relative_path: str = Field(..., min_length=1, max_length=1000)
    role: str = "stem"
    sort_order: int | None = None
    is_primary: bool = False


class CachedImageAsset(BaseModel):
    """One temporary image that can be inserted into a question."""

    relative_path: str
    filename: str
    file_path: str
    mime_type: str = "application/octet-stream"
    size: int = 0


class AvailableImageAsset(BaseModel):
    """One reusable image from the canonical asset catalog."""

    asset_id: str
    filename: str
    file_path: str
    mime_type: str | None = None


class CacheUploadResponse(BaseModel):
    """Images extracted from files dropped into the temporary image cache."""

    images: list[CachedImageAsset] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


class ReplaceImageRequest(BaseModel):
    old_asset_id: str
    new_asset_id: str


class UpdateImageRequest(BaseModel):
    role: str | None = None
    sort_order: int | None = None
    placeholder_key: str | None = None
    display_scale: float | None = Field(default=None, ge=25, le=100)
    is_primary: bool | None = None
    description: str | None = None


class ReorderRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1)


class PlaceholderIssue(BaseModel):
    type: str  # missing_image | unreferenced_image | duplicate_placeholder
    message: str
    fig_uuid: str | None = None


class ValidationResponse(BaseModel):
    valid: bool = True
    issues: list[PlaceholderIssue] = Field(default_factory=list)
