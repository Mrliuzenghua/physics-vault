"""Restore endpoint: upload a migration .zip and restore database + assets."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from ..paths import default_assets_dir, default_backups_dir, default_db_path
from ..schemas.restore_package import RestorePackageResponse
from ..services.restore_package import RestorePackageService


def build_restore_package_router(
    db_path: str | None = None,
    assets_path: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system-restore"])

    @router.post(
        "/restore-package",
        summary="导入恢复题库包",
        description=(
            "上传一个由系统导出的 .zip 迁移包，校验结构、备份当前数据、"
            "然后将数据库和素材恢复到当前系统目录。"
            "恢复前会自动创建旧数据备份，失败时当前数据不受影响。"
        ),
        response_model=RestorePackageResponse,
    )
    async def restore_package(file: UploadFile) -> RestorePackageResponse:
        # ── Resolve paths ──
        project_root = Path(__file__).resolve().parents[4]
        vault_root = project_root.parents[1]

        resolved_db = (
            Path(db_path)
            if db_path
            else vault_root / "02-数据库" / "01-db" / "physics_vault.sqlite3"
        )
        resolved_assets = (
            Path(assets_path)
            if assets_path
            else vault_root / "02-数据库" / "02-素材"
        )
        resolved_backup = vault_root / "02-数据库" / "03-backups"

        # ── Basic validation ──
        if not file.filename or not file.filename.lower().endswith(".zip"):
            raise HTTPException(
                status_code=400,
                detail={"message": "仅支持 .zip 格式的迁移包", "filename": file.filename},
            )

        # ── Read file content ──
        try:
            zip_data = await file.read()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"message": "文件读取失败", "detail": str(exc)},
            ) from exc

        if not zip_data:
            raise HTTPException(
                status_code=400,
                detail={"message": "上传的文件为空", "filename": file.filename},
            )

        # ── Run restore pipeline ──
        svc = RestorePackageService(
            db_path=str(resolved_db),
            assets_path=str(resolved_assets),
            backup_root=str(resolved_backup),
        )
        result = svc.restore(zip_data)

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": result.error or "恢复失败",
                    "backup_path": result.backup_path,
                    "warnings": result.warnings,
                },
            )

        return RestorePackageResponse(
            success=result.success,
            started_at=result.started_at,
            finished_at=result.finished_at,
            database_file=result.database_file,
            asset_count=result.asset_count,
            backup_path=result.backup_path,
            warnings=result.warnings,
        )

    return router
