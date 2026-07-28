"""Asset scanning, reference detection, and cleanup logic."""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_assets_dir, default_db_path

from ..schemas.assets_manager import (
    AssetItem,
    AssetListResponse,
    AssetStats,
    CleanupResponse,
    DeleteAssetResponse,
)

logger = logging.getLogger(__name__)

_DEFAULT_ASSETS_DIR = default_assets_dir()
_DEFAULT_DB_PATH = default_db_path()

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class AssetsManagerService:
    """Scans the assets directory and compares against database references."""

    def __init__(
        self,
        assets_dir: str | None = None,
        db_path: str | None = None,
    ) -> None:
        self._assets_dir = Path(assets_dir) if assets_dir else _DEFAULT_ASSETS_DIR
        resolved_db = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path = resolved_db if resolved_db.exists() else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_asset_list(self, filter_mode: str = "all", keyword: str = "") -> AssetListResponse:
        """Return assets with reference status and stats."""
        if not self._assets_dir.exists():
            raise FileNotFoundError(f"素材目录不存在: {self._assets_dir}")
        if not self._assets_dir.is_dir():
            raise NotADirectoryError(f"素材路径不是目录: {self._assets_dir}")

        # Build reference set from DB (relative paths found in questions)
        ref_set = self._build_reference_set()

        # Scan filesystem
        assets: list[AssetItem] = []
        total_size = 0

        for entry in sorted(self._assets_dir.rglob("*")):
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                continue

            # Relative path from assets root
            try:
                rel_path = entry.relative_to(self._assets_dir).as_posix()
            except ValueError:
                rel_path = entry.name

            # Check if this file is referenced by any question
            # We check multiple forms: the relative path, the filename alone, the full path
            ref_count = self._count_references(entry, rel_path, ref_set)

            size = entry.stat().st_size
            total_size += size

            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC).isoformat()

            asset = AssetItem(
                filename=entry.name,
                relative_path=rel_path,
                size_bytes=size,
                mime_type=_MIME_MAP.get(ext, "application/octet-stream"),
                modified_at=mtime,
                is_referenced=ref_count > 0,
                reference_count=ref_count,
            )
            assets.append(asset)

        # Apply filters
        if filter_mode == "referenced":
            assets = [a for a in assets if a.is_referenced]
        elif filter_mode == "unreferenced":
            assets = [a for a in assets if not a.is_referenced]

        if keyword:
            kw = keyword.lower()
            assets = [a for a in assets if kw in a.filename.lower() or kw in a.relative_path.lower()]

        ref_count = sum(1 for a in assets if a.is_referenced)
        unreferenced_count = len(assets) - ref_count

        return AssetListResponse(
            assets=assets,
            stats=AssetStats(
                total=len(assets),
                referenced=ref_count,
                unreferenced=unreferenced_count,
                total_size_bytes=total_size,
            ),
        )

    def cleanup_unreferenced(self) -> CleanupResponse:
        """Delete all unreferenced asset files. Returns count + errors."""
        if not self._assets_dir.exists():
            raise FileNotFoundError(f"素材目录不存在: {self._assets_dir}")

        ref_set = self._build_reference_set()
        deleted = 0
        freed = 0
        errors: list[str] = []

        for entry in sorted(self._assets_dir.rglob("*")):
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in _SUPPORTED_EXTENSIONS:
                continue

            try:
                rel_path = entry.relative_to(self._assets_dir).as_posix()
            except ValueError:
                rel_path = entry.name

            if self._count_references(entry, rel_path, ref_set) > 0:
                continue  # still referenced — skip

            # Safety check: ensure within assets dir
            if not self._is_safe_to_delete(entry):
                errors.append(f"安全校验拦截: {entry}")
                continue

            try:
                size = entry.stat().st_size
                entry.unlink()
                deleted += 1
                freed += size
                logger.info("Deleted unreferenced asset: %s", entry)
            except OSError as exc:
                errors.append(f"删除失败 {entry}: {exc}")

        return CleanupResponse(deleted_count=deleted, freed_bytes=freed, errors=errors)

    def delete_single(self, filename: str) -> DeleteAssetResponse:
        """Delete a single asset file — only if unreferenced."""
        # Normalize: only allow the filename (not a path) to prevent traversal
        safe_name = Path(filename).name
        if safe_name != filename:
            return DeleteAssetResponse(success=False, message="文件名包含非法路径字符")

        target = self._assets_dir / safe_name

        # Walk to find the actual file
        actual_path: Path | None = None
        for entry in self._assets_dir.rglob(safe_name):
            if entry.is_file() and entry.name == safe_name:
                actual_path = entry
                break

        if actual_path is None:
            return DeleteAssetResponse(success=False, message=f"文件不存在: {safe_name}")

        if not self._is_safe_to_delete(actual_path):
            return DeleteAssetResponse(success=False, message="安全校验拦截：文件不在素材目录内")

        # Check reference
        ref_set = self._build_reference_set()
        try:
            rel_path = actual_path.relative_to(self._assets_dir).as_posix()
        except ValueError:
            rel_path = actual_path.name

        if self._count_references(actual_path, rel_path, ref_set) > 0:
            return DeleteAssetResponse(
                success=False,
                message="该素材仍被题目引用，不能删除。请先移除引用关系。",
            )

        try:
            actual_path.unlink()
            return DeleteAssetResponse(success=True, message=f"已删除: {safe_name}")
        except OSError as exc:
            return DeleteAssetResponse(success=False, message=f"删除失败: {exc}")

    # ------------------------------------------------------------------
    # Reference detection
    # ------------------------------------------------------------------

    def _build_reference_set(self) -> dict[str, set[str]]:
        """Build a mapping of {referenced_path → set of question_ids} from the DB.

        Returns an empty dict if the database is unavailable.
        """
        if self._db_path is None or not self._db_path.exists():
            logger.warning("Database not found, reference set is empty")
            return {}

        ref_map: dict[str, set[str]] = {}

        try:
            with closing(connect_db(self._db_path, writable=False)) as conn:
                # Source 1: image_assets.file_path
                try:
                    rows = conn.execute(
                        "SELECT file_path FROM image_assets WHERE file_path IS NOT NULL AND file_path != ''"
                    ).fetchall()
                    for row in rows:
                        path = str(row["file_path"]).strip()
                        if path:
                            ref_map.setdefault(path, set()).add("ia")
                except sqlite3.OperationalError:
                    pass

                # Source 2: question_assets join image_assets
                try:
                    rows = conn.execute(
                        """
                        SELECT ia.file_path
                        FROM question_assets qa
                        INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
                        WHERE ia.file_path IS NOT NULL AND ia.file_path != ''
                        """
                    ).fetchall()
                    for row in rows:
                        path = str(row["file_path"]).strip()
                        if path:
                            ref_map.setdefault(path, set()).add("qa")
                except sqlite3.OperationalError:
                    pass

                # Source 3: questions table — figures stored as JSON in question_text_index
                try:
                    rows = conn.execute(
                        """
                        SELECT image_filenames_json FROM question_text_index
                        WHERE image_filenames_json IS NOT NULL AND image_filenames_json != ''
                        """
                    ).fetchall()
                    for row in rows:
                        try:
                            import json

                            filenames = json.loads(row["image_filenames_json"])
                            if isinstance(filenames, list):
                                for f in filenames:
                                    path = str(f).strip()
                                    if path:
                                        ref_map.setdefault(path, set()).add("qn")
                        except (json.JSONDecodeError, TypeError):
                            pass
                except sqlite3.OperationalError:
                    pass

                # Source 4: questions with figures in review/draft — not in DB yet, skip

        except sqlite3.Error as exc:
            logger.warning("Database error during reference scan: %s", exc)

        return ref_map

    def _count_references(
        self,
        entry: Path,
        rel_path: str,
        ref_set: dict[str, set[str]],
    ) -> int:
        """Count how many questions reference this asset file.

        Checks multiple path forms to handle different storage conventions.
        """
        count = 0

        # Check exact relative path
        if rel_path in ref_set:
            count += len(ref_set[rel_path])

        # Check filename alone (some records only store basename)
        name = entry.name
        if name in ref_set and name != rel_path:
            count += len(ref_set[name])

        # Check if any ref path ends with this filename
        for ref_path, refs in ref_set.items():
            if ref_path == rel_path or ref_path == name:
                continue
            if ref_path.endswith("/" + name) or ref_path == name:
                count += len(refs)

        return count

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _is_safe_to_delete(self, path: Path) -> bool:
        """Ensure the file is within the assets directory."""
        try:
            path.resolve().relative_to(self._assets_dir.resolve())
            return True
        except ValueError:
            return False
