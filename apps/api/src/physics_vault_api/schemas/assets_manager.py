from __future__ import annotations

from pydantic import BaseModel, Field


class AssetItem(BaseModel):
    """A single asset file with its reference status."""

    filename: str = Field(..., description="File name (excluding directory)")
    relative_path: str = Field(..., description="Path relative to assets root")
    size_bytes: int = Field(default=0, description="File size in bytes")
    mime_type: str = Field(default="", description="MIME type inferred from extension")
    modified_at: str = Field(default="", description="ISO timestamp of last modification")
    is_referenced: bool = Field(default=False, description="Whether any question references this asset")
    reference_count: int = Field(default=0, description="Number of questions referencing this asset")


class AssetStats(BaseModel):
    total: int = 0
    referenced: int = 0
    unreferenced: int = 0
    total_size_bytes: int = 0


class AssetListResponse(BaseModel):
    assets: list[AssetItem] = Field(default_factory=list)
    stats: AssetStats = Field(default_factory=AssetStats)


class CleanupResponse(BaseModel):
    deleted_count: int = 0
    freed_bytes: int = 0
    errors: list[str] = Field(default_factory=list)


class DeleteAssetResponse(BaseModel):
    success: bool
    message: str = ""
