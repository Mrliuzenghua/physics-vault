"""Restore package service: receive an uploaded migration .zip, validate its
structure, back up current data, then restore the database and assets.

Expected package structure (produced by ``ExportPackageService``):

    database/<db_filename>
    assets/<relative/path/...>
    manifest.json
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

EXPECTED_FORMAT = "physics-vault-v1"


@dataclass(slots=True)
class RestoreResult:
    success: bool
    started_at: str
    finished_at: str
    database_file: str | None = None
    asset_count: int = 0
    backup_path: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class RestorePackageService:
    """Validates and restores a migration package into the current system."""

    def __init__(
        self,
        db_path: str,
        assets_path: str,
        backup_root: str | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._assets_path = Path(assets_path)
        self._backup_root = Path(backup_root) if backup_root else Path(tempfile.gettempdir()) / "physics-vault-backups"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def restore(self, zip_data: bytes) -> RestoreResult:
        """Run the full restore pipeline on raw zip bytes.

        Returns a ``RestoreResult`` describing the outcome.  On failure the
        current database and assets are left untouched (a backup is always
        created *before* any destructive writes).
        """
        started_at = _utc_now()

        # ── 1. Save zip to temp ──────────────────────────────────────
        tmp_dir = Path(tempfile.mkdtemp(prefix="pv-restore-"))
        zip_path = tmp_dir / "restore.zip"
        try:
            zip_path.write_bytes(zip_data)
        except OSError as exc:
            return self._fail(started_at, f"无法写入临时文件: {exc}")

        # ── 2. Extract ───────────────────────────────────────────────
        extract_dir = tmp_dir / "extracted"
        try:
            extract_dir.mkdir()
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, f"压缩包损坏或不是有效的 ZIP 文件: {exc}")
        except OSError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, f"解压失败: {exc}")

        # ── 3. Validate structure ────────────────────────────────────
        manifest_path = extract_dir / "manifest.json"
        if not manifest_path.is_file():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, "导入包缺少 manifest.json 文件，结构不合法")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, f"manifest.json 无法解析: {exc}")

        fmt = manifest.get("export_format", "")
        if fmt != EXPECTED_FORMAT:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, f"不支持的导出格式: {fmt}（期望 {EXPECTED_FORMAT}）")

        db_arcname = manifest.get("database_file", "")
        db_in_zip = extract_dir / db_arcname
        if not db_arcname or not db_in_zip.is_file():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, f"导入包中缺少数据库文件: {db_arcname}")

        assets_arcname = manifest.get("assets_dir", "assets/")
        assets_in_zip = extract_dir / assets_arcname
        asset_count_in_manifest = int(manifest.get("asset_count", 0))

        # Count actual files under assets/
        actual_asset_count = 0
        if assets_in_zip.is_dir():
            actual_asset_count = sum(1 for _ in assets_in_zip.rglob("*") if _.is_file())

        warnings: list[str] = []
        if actual_asset_count != asset_count_in_manifest:
            warnings.append(
                f"素材数量与清单不一致: manifest 声明 {asset_count_in_manifest} 个，实际找到 {actual_asset_count} 个"
            )

        # ── 4. Backup current data ───────────────────────────────────
        backup_path = self._backup_current(started_at)
        if backup_path is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, "备份当前数据失败，已中止恢复操作")

        # ── 5. Restore database ──────────────────────────────────────
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(db_in_zip), str(self._db_path))
            logger.info("Database restored from %s", db_in_zip)
        except OSError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return self._fail(started_at, f"恢复数据库失败: {exc}", backup_path=str(backup_path))

        # ── 6. Restore assets ────────────────────────────────────────
        restored_asset_count = 0
        if assets_in_zip.is_dir():
            # Remove old assets first, then copy new ones
            if self._assets_path.exists():
                shutil.rmtree(str(self._assets_path), ignore_errors=True)
            self._assets_path.mkdir(parents=True, exist_ok=True)

            try:
                for src_file in assets_in_zip.rglob("*"):
                    if not src_file.is_file():
                        continue
                    rel = src_file.relative_to(assets_in_zip)
                    dst = self._assets_path / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_file), str(dst))
                    restored_asset_count += 1
            except OSError as exc:
                # Attempt to restore backup on partial failure
                warnings.append(f"素材恢复失败: {exc}。数据库已恢复，旧素材备份在 {backup_path}")
        else:
            warnings.append("导入包中不包含素材目录，仅恢复了数据库")

        # ── 7. Clean up ──────────────────────────────────────────────
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return RestoreResult(
            success=True,
            started_at=started_at,
            finished_at=_utc_now(),
            database_file=str(db_arcname),
            asset_count=restored_asset_count,
            backup_path=str(backup_path),
            warnings=warnings if warnings else [],
        )

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def _backup_current(self, started_at: str) -> Path | None:
        """Copy current database and assets into a timestamped backup dir.

        Returns the backup directory path, or ``None`` if the directory
        could not be created.
        """
        ts = started_at.replace(":", "-").replace("T", "-")[:19]
        backup_dir = self._backup_root / f"pre-restore-{ts}"

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Failed to create backup directory %s", backup_dir)
            return None

        # Copy database
        if self._db_path.is_file():
            try:
                db_backup = backup_dir / self._db_path.name
                shutil.copy2(str(self._db_path), str(db_backup))
                logger.info("Backed up database to %s", db_backup)
            except OSError:
                logger.exception("Failed to backup database")
                shutil.rmtree(backup_dir, ignore_errors=True)
                return None

        # Copy assets
        if self._assets_path.is_dir():
            try:
                assets_backup = backup_dir / self._assets_path.name
                shutil.copytree(
                    str(self._assets_path),
                    str(assets_backup),
                    symlinks=False,
                    dirs_exist_ok=True,
                )
                logger.info("Backed up assets to %s", assets_backup)
            except OSError:
                logger.exception("Failed to backup assets — database backup OK")
                # Continue despite asset backup failure; the db backup succeeded

        return backup_dir

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fail(self, started_at: str, error: str, **extra: object) -> RestoreResult:
        return RestoreResult(
            success=False,
            started_at=started_at,
            finished_at=_utc_now(),
            error=error,
            **extra,  # type: ignore[arg-type]
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
