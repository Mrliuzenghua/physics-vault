"""Export package service: bundle the SQLite database and assets directory
into a single timestamped .zip archive for migration / backup.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)

APP_NAME = "Physics Vault"
APP_VERSION = "1.0.0"


class ExportPackageService:
    """Produces a portable .zip file containing the database and assets."""

    def __init__(
        self,
        db_path: str,
        assets_path: str,
        app_name: str = APP_NAME,
        app_version: str = APP_VERSION,
    ) -> None:
        self._db_path = Path(db_path)
        self._assets_path = Path(assets_path)
        self._app_name = app_name
        self._app_version = app_version

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_export(self) -> Path:
        """Validate inputs, build the zip archive, and return its Path.

        Raises ``HTTPException`` on any validation or I/O error.
        """
        self._validate()

        # Timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        zip_filename = f"physics-vault-export-{timestamp}.zip"

        tmp_dir = Path(tempfile.mkdtemp(prefix="pv-export-"))
        zip_path = tmp_dir / zip_filename

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # ── Database ──
                zf.write(
                    self._db_path,
                    arcname=f"database/{self._db_path.name}",
                )

                # ── Assets ──
                asset_count = self._add_assets(zf)

                # ── Manifest ──
                manifest = self._build_manifest(
                    db_filename=self._db_path.name,
                    asset_count=asset_count,
                    timestamp=timestamp,
                )
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

            logger.info(
                "Export package created: %s (%d assets, %.1f KB)",
                zip_path.name,
                asset_count,
                zip_path.stat().st_size / 1024,
            )
            return zip_path

        except Exception:
            # Clean up on failure
            if zip_path.exists():
                zip_path.unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        if not self._db_path.exists() or not self._db_path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "message": f"数据库文件不存在: {self._db_path}",
                    "path": str(self._db_path),
                },
            )
        if not self._assets_path.exists() or not self._assets_path.is_dir():
            raise HTTPException(
                status_code=404,
                detail={
                    "message": f"素材目录不存在: {self._assets_path}",
                    "path": str(self._assets_path),
                },
            )

    # ------------------------------------------------------------------
    # Asset collection
    # ------------------------------------------------------------------

    def _add_assets(self, zf: zipfile.ZipFile) -> int:
        """Add all files under the assets directory, preserving relative paths."""
        count = 0
        for file_path in self._assets_path.rglob("*"):
            if not file_path.is_file():
                continue
            arcname = f"assets/{file_path.relative_to(self._assets_path)}"
            zf.write(file_path, arcname=arcname)
            count += 1
        return count

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _build_manifest(
        self,
        db_filename: str,
        asset_count: int,
        timestamp: str,
    ) -> dict:
        return {
            "app_name": self._app_name,
            "app_version": self._app_version,
            "exported_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "database_file": f"database/{db_filename}",
            "assets_dir": "assets/",
            "asset_count": asset_count,
            "export_format": "physics-vault-v1",
        }
