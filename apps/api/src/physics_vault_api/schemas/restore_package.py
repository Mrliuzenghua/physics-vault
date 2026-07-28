from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RestorePackageResponse(BaseModel):
    success: bool = Field(..., description="恢复是否成功")
    started_at: str = Field(..., description="恢复开始时间 (ISO 8601 UTC)")
    finished_at: str = Field(..., description="恢复结束时间 (ISO 8601 UTC)")
    database_file: str | None = Field(default=None, description="恢复的数据库文件名")
    asset_count: int = Field(default=0, description="恢复的素材文件数量")
    backup_path: str | None = Field(default=None, description="旧数据备份目录路径")
    error: str | None = Field(default=None, description="失败原因（仅当 success=false）")
    warnings: list[str] = Field(default_factory=list, description="非致命警告信息")
