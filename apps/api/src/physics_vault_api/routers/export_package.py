"""Export endpoint: download a portable .zip archive of the database + assets."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..paths import default_assets_dir, default_db_path
from ..services.export_package import ExportPackageService


def _resolve_export_paths(db_path: str, assets_path: str) -> tuple[Path, Path]:
    return (
        Path(db_path) if db_path else default_db_path(),
        Path(assets_path) if assets_path else default_assets_dir(),
    )


def build_export_package_router() -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system-export"])

    @router.get(
        "/export-package",
        response_class=FileResponse,
        summary="导出题库包",
        description=(
            "将数据库文件和素材目录打包为一个 .zip 文件下载。"
            "可指定自定义 db_path 和 assets_path，留空则使用默认路径。"
        ),
    )
    async def export_package(
        db_path: str = Query(
            default="",
            description="数据库文件绝对路径，留空使用系统默认路径",
        ),
        assets_path: str = Query(
            default="",
            description="素材目录绝对路径，留空使用系统默认路径",
        ),
    ) -> FileResponse:
        # ── Resolve paths ──
        resolved_db, resolved_assets = _resolve_export_paths(db_path, assets_path)

        # ── Build export ──
        try:
            svc = ExportPackageService(
                db_path=str(resolved_db),
                assets_path=str(resolved_assets),
            )
            zip_path = svc.build_export()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "导出打包失败", "detail": str(exc)},
            ) from exc

        # ── Return file, then schedule cleanup ──
        temp_dir = zip_path.parent

        async def _cleanup():
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception:
                pass  # best-effort cleanup

        response = FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=zip_path.name,
            background=_cleanup(),
        )
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{zip_path.name}"'
        )
        return response

    return router
