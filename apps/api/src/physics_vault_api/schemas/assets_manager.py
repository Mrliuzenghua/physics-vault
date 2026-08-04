from __future__ import annotations

from pydantic import BaseModel, Field


class AssetItem(BaseModel):
    """A single asset file with its reference status."""

    filename: str = Field(..., description="File name (excluding directory)")
    relative_path: str = Field(..., description="Path relative to assets root")
    source: str = Field(default="question_bank", description="Asset source: question_bank or import_batch")
    batch_id: str | None = Field(default=None, description="Owning import batch, when applicable")
    size_bytes: int = Field(default=0, description="File size in bytes")
    mime_type: str = Field(default="", description="MIME type inferred from extension")
    modified_at: str = Field(default="", description="ISO timestamp of last modification")
    is_referenced: bool = Field(default=False, description="Whether any question references this asset")
    reference_count: int = Field(default=0, description="Number of questions referencing this asset")
    reference_question_ids: list[str] = Field(default_factory=list, description="Question ids referencing this asset")
    lifecycle_status: str = Field(
        default="unknown",
        description="referenced, unreferenced, staged, imported, or unknown",
    )


class AssetStats(BaseModel):
    total: int = 0
    referenced: int = 0
    unreferenced: int = 0
    total_size_bytes: int = 0


class AssetBatchSummary(BaseModel):
    batch_id: str
    asset_count: int = 0
    referenced: int = 0
    unreferenced: int = 0
    total_size_bytes: int = 0
    modified_at: str = ""


class AssetPagination(BaseModel):
    page: int = 1
    page_size: int = 60
    total_items: int = 0
    total_pages: int = 0


class AssetListResponse(BaseModel):
    assets: list[AssetItem] = Field(default_factory=list)
    stats: AssetStats = Field(default_factory=AssetStats)
    library_stats: AssetStats = Field(default_factory=AssetStats)
    batches: list[AssetBatchSummary] = Field(default_factory=list)
    pagination: AssetPagination = Field(default_factory=AssetPagination)
    reference_scan_available: bool = True


class CleanupPreviewResponse(BaseModel):
    candidate_count: int = 0
    reclaimable_bytes: int = 0
    protected_count: int = 0
    scope: str = "question_bank"


class CacheCleanupPreviewResponse(BaseModel):
    batch_id: str | None = None
    batch_count: int = 0
    candidate_count: int = 0
    reclaimable_bytes: int = 0
    protected_count: int = 0
    active_batches: list[str] = Field(default_factory=list)


class CacheCleanupRequest(BaseModel):
    batch_id: str | None = None


class DuplicateAssetGroup(BaseModel):
    content_hash: str
    copies: int = 0
    size_bytes: int = 0
    reclaimable_bytes: int = 0
    paths: list[str] = Field(default_factory=list)


class StorageAnalysisResponse(BaseModel):
    scanned_files: int = 0
    duplicate_groups: int = 0
    duplicate_files: int = 0
    reclaimable_bytes: int = 0
    tiny_files: list[str] = Field(default_factory=list)
    corrupt_files: list[str] = Field(default_factory=list)
    oversized_files: list[str] = Field(default_factory=list)
    groups: list[DuplicateAssetGroup] = Field(default_factory=list)


class CleanupResponse(BaseModel):
    deleted_count: int = 0
    freed_bytes: int = 0
    errors: list[str] = Field(default_factory=list)


class DeleteAssetResponse(BaseModel):
    success: bool
    message: str = ""
