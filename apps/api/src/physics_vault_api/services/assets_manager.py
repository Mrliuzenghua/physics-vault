"""Asset scanning, reference detection, and cleanup logic."""

from __future__ import annotations

import json
import hashlib
import logging
import math
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..database import connect_db
from ..paths import default_assets_dir, default_db_path, default_import_batches_dir, project_root

from ..schemas.assets_manager import (
    AssetBatchSummary,
    AssetItem,
    AssetListResponse,
    AssetPagination,
    AssetStats,
    CacheCleanupPreviewResponse,
    CleanupPreviewResponse,
    CleanupResponse,
    DeleteAssetResponse,
    DuplicateAssetGroup,
    StorageAnalysisResponse,
)

logger = logging.getLogger(__name__)

_DEFAULT_ASSETS_DIR = default_assets_dir()
_DEFAULT_DB_PATH = default_db_path()
_DEFAULT_IMPORT_BATCHES_DIR = default_import_batches_dir()
_PROJECT_ROOT = project_root()

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
        import_batches_dir: str | None = None,
    ) -> None:
        self._assets_dir = Path(assets_dir) if assets_dir else _DEFAULT_ASSETS_DIR
        self._import_batches_dir = Path(import_batches_dir) if import_batches_dir else _DEFAULT_IMPORT_BATCHES_DIR
        resolved_db = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path = resolved_db if resolved_db.exists() else None
        self._scan_cache: tuple[float, list[AssetItem], bool] | None = None
        self._cache_ttl_seconds = 10.0
        self._analysis_cache: dict[str, tuple[float, StorageAnalysisResponse]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_asset_list(
        self,
        filter_mode: str = "all",
        keyword: str = "",
        source: str = "all",
        batch_id: str = "",
        sort_by: str = "modified_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 60,
        force_refresh: bool = False,
    ) -> AssetListResponse:
        """Return a filtered, sorted, and paginated asset list."""
        all_assets, reference_scan_available = self._scan_assets(force_refresh=force_refresh)
        assets = list(all_assets)

        if source != "all":
            assets = [asset for asset in assets if asset.source == source]
        if filter_mode == "referenced":
            assets = [asset for asset in assets if asset.is_referenced]
        elif filter_mode == "unreferenced":
            assets = [asset for asset in assets if asset.lifecycle_status in {"unreferenced", "staged"}]
        if batch_id:
            assets = [asset for asset in assets if asset.batch_id == batch_id]
        if keyword:
            kw = keyword.lower()
            assets = [asset for asset in assets if kw in asset.filename.lower() or kw in asset.relative_path.lower()]

        sort_key = {
            "name": lambda item: (item.filename.lower(), item.relative_path.lower()),
            "size_bytes": lambda item: (item.size_bytes, item.filename.lower()),
            "reference_count": lambda item: (item.reference_count, item.filename.lower()),
            "modified_at": lambda item: (item.modified_at, item.filename.lower()),
        }.get(sort_by, lambda item: (item.modified_at, item.filename.lower()))
        assets.sort(key=sort_key, reverse=sort_order == "desc")

        filtered_stats = self._stats_for(assets)
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        total_pages = math.ceil(len(assets) / page_size) if assets else 0
        start = (page - 1) * page_size

        return AssetListResponse(
            assets=assets[start:start + page_size],
            stats=filtered_stats,
            library_stats=self._stats_for(all_assets),
            batches=self._batch_summaries(all_assets),
            pagination=AssetPagination(
                page=page,
                page_size=page_size,
                total_items=len(assets),
                total_pages=total_pages,
            ),
            reference_scan_available=reference_scan_available,
        )

    def get_cleanup_preview(self) -> CleanupPreviewResponse:
        """Describe the safe question-bank cleanup without deleting files."""
        assets, reference_scan_available = self._scan_assets(force_refresh=True)
        question_bank_assets = [asset for asset in assets if asset.source == "question_bank"]
        if not reference_scan_available:
            return CleanupPreviewResponse(protected_count=len(question_bank_assets))
        candidates = [asset for asset in question_bank_assets if asset.lifecycle_status == "unreferenced"]
        return CleanupPreviewResponse(
            candidate_count=len(candidates),
            reclaimable_bytes=sum(asset.size_bytes for asset in candidates),
            protected_count=len(question_bank_assets) - len(candidates),
        )

    def get_import_cache_cleanup_preview(self, batch_id: str = "") -> CacheCleanupPreviewResponse:
        """Preview deletion of unreferenced, inactive import-cache images."""
        assets, reference_scan_available = self._scan_assets(force_refresh=True)
        import_assets = [
            asset for asset in assets
            if asset.source == "import_batch" and (not batch_id or asset.batch_id == batch_id)
        ]
        batch_ids = {asset.batch_id for asset in import_assets if asset.batch_id}
        active_batches = sorted(batch for batch in batch_ids if self._is_batch_active(batch))
        if not reference_scan_available:
            return CacheCleanupPreviewResponse(
                batch_id=batch_id or None,
                protected_count=len(import_assets),
                active_batches=active_batches,
            )
        candidates = [
            asset for asset in import_assets
            if not asset.is_referenced and asset.batch_id not in active_batches
        ]
        return CacheCleanupPreviewResponse(
            batch_id=batch_id or None,
            batch_count=len({asset.batch_id for asset in candidates if asset.batch_id}),
            candidate_count=len(candidates),
            reclaimable_bytes=sum(asset.size_bytes for asset in candidates),
            protected_count=len(import_assets) - len(candidates),
            active_batches=active_batches,
        )

    def cleanup_import_cache(self, batch_id: str = "") -> CleanupResponse:
        """Delete only unreferenced image files from inactive import batches."""
        ref_set, reference_scan_available = self._build_reference_set()
        if not reference_scan_available:
            return CleanupResponse(errors=["Reference database unavailable; cache cleanup was not performed."])

        deleted = 0
        freed = 0
        errors: list[str] = []
        active_cache: dict[str, bool] = {}
        for entry, rel_path, source in self._iter_asset_files():
            if source != "import_batch":
                continue
            item_batch_id = self._batch_id_from_path(rel_path)
            if batch_id and item_batch_id != batch_id:
                continue
            if not item_batch_id:
                errors.append(f"Batch id could not be resolved: {rel_path}")
                continue
            if item_batch_id not in active_cache:
                active_cache[item_batch_id] = self._is_batch_active(item_batch_id)
            is_active = active_cache[item_batch_id]
            if is_active or self._reference_ids(entry, rel_path, ref_set, source):
                continue
            if not self._is_safe_to_delete(entry):
                errors.append(f"Safety check blocked: {entry}")
                continue
            try:
                size = entry.stat().st_size
                entry.unlink()
                deleted += 1
                freed += size
            except OSError as exc:
                errors.append(f"Delete failed {entry}: {exc}")

        self._scan_cache = None
        self._analysis_cache.clear()
        return CleanupResponse(deleted_count=deleted, freed_bytes=freed, errors=errors)

    def analyze_storage(self, source: str = "all", force_refresh: bool = False) -> StorageAnalysisResponse:
        """Hash and validate managed images without changing any files."""
        cached = self._analysis_cache.get(source)
        now = time.monotonic()
        if not force_refresh and cached and now - cached[0] < 300:
            return cached[1]

        hashes: dict[str, list[tuple[str, int]]] = {}
        tiny_files: list[str] = []
        corrupt_files: list[str] = []
        oversized_files: list[str] = []
        scanned = 0
        for entry, rel_path, asset_source in self._iter_asset_files():
            if source != "all" and asset_source != source:
                continue
            scanned += 1
            try:
                size = entry.stat().st_size
                digest = hashlib.sha256()
                with entry.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                with Image.open(entry) as image:
                    image.verify()
            except (OSError, UnidentifiedImageError, ValueError):
                corrupt_files.append(rel_path)
                continue
            hashes.setdefault(digest.hexdigest(), []).append((rel_path, size))
            if size <= 512:
                tiny_files.append(rel_path)
            if size >= 10 * 1024 * 1024:
                oversized_files.append(rel_path)

        groups = [DuplicateAssetGroup(
            content_hash=content_hash,
            copies=len(items),
            size_bytes=items[0][1],
            reclaimable_bytes=(len(items) - 1) * items[0][1],
            paths=[item[0] for item in items],
        ) for content_hash, items in hashes.items() if len(items) > 1]
        groups.sort(key=lambda group: group.reclaimable_bytes, reverse=True)
        response = StorageAnalysisResponse(
            scanned_files=scanned,
            duplicate_groups=len(groups),
            duplicate_files=sum(group.copies - 1 for group in groups),
            reclaimable_bytes=sum(group.reclaimable_bytes for group in groups),
            tiny_files=tiny_files[:100],
            corrupt_files=corrupt_files[:100],
            oversized_files=oversized_files[:100],
            groups=groups[:100],
        )
        self._analysis_cache[source] = (now, response)
        return response

    def _scan_assets(self, force_refresh: bool = False) -> tuple[list[AssetItem], bool]:
        now = time.monotonic()
        if not force_refresh and self._scan_cache and now - self._scan_cache[0] < self._cache_ttl_seconds:
            return self._scan_cache[1], self._scan_cache[2]
        if not self._assets_dir.exists() and not self._import_batches_dir.exists():
            raise FileNotFoundError(f"Asset folders do not exist: {self._assets_dir}")
        if self._assets_dir.exists() and not self._assets_dir.is_dir():
            raise NotADirectoryError(f"Asset path is not a directory: {self._assets_dir}")

        ref_set, reference_scan_available = self._build_reference_set()
        assets: list[AssetItem] = []
        for entry, rel_path, source in self._iter_asset_files():
            try:
                stat = entry.stat()
            except OSError:
                continue
            reference_ids = sorted(self._reference_ids(entry, rel_path, ref_set, source))
            if not reference_scan_available:
                lifecycle_status = "unknown"
            elif source == "import_batch":
                lifecycle_status = "imported" if reference_ids else "staged"
            else:
                lifecycle_status = "referenced" if reference_ids else "unreferenced"
            assets.append(AssetItem(
                filename=entry.name,
                relative_path=rel_path,
                source=source,
                batch_id=self._batch_id_from_path(rel_path) if source == "import_batch" else None,
                size_bytes=stat.st_size,
                mime_type=_MIME_MAP.get(entry.suffix.lower(), "application/octet-stream"),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                is_referenced=bool(reference_ids),
                reference_count=len(reference_ids),
                reference_question_ids=reference_ids,
                lifecycle_status=lifecycle_status,
            ))
        self._scan_cache = (now, assets, reference_scan_available)
        return assets, reference_scan_available

    @staticmethod
    def _stats_for(assets: list[AssetItem]) -> AssetStats:
        return AssetStats(
            total=len(assets),
            referenced=sum(1 for asset in assets if asset.is_referenced),
            unreferenced=sum(1 for asset in assets if asset.lifecycle_status in {"unreferenced", "staged"}),
            total_size_bytes=sum(asset.size_bytes for asset in assets),
        )

    @staticmethod
    def _batch_summaries(assets: list[AssetItem]) -> list[AssetBatchSummary]:
        grouped: dict[str, list[AssetItem]] = {}
        for asset in assets:
            if asset.source == "import_batch" and asset.batch_id:
                grouped.setdefault(asset.batch_id, []).append(asset)
        summaries = [AssetBatchSummary(
            batch_id=batch_id,
            asset_count=len(items),
            referenced=sum(1 for item in items if item.is_referenced),
            unreferenced=sum(1 for item in items if item.lifecycle_status == "staged"),
            total_size_bytes=sum(item.size_bytes for item in items),
            modified_at=max((item.modified_at for item in items), default=""),
        ) for batch_id, items in grouped.items()]
        return sorted(summaries, key=lambda item: item.modified_at, reverse=True)

    @staticmethod
    def _batch_id_from_path(path: str) -> str | None:
        parts = path.replace("\\", "/").split("/")
        try:
            index = parts.index("import-batches")
        except ValueError:
            return None
        return parts[index + 1] if index + 1 < len(parts) else None

    def _is_batch_active(self, batch_id: str) -> bool:
        metadata_path = self._import_batches_dir / batch_id / "status.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        status = str(metadata.get("status") or "").strip().lower()
        return (
            status in {"created", "uploaded", "pending", "running", "processing", "recognizing", "ai_review"}
            or status.endswith("_running")
        )

    def cleanup_unreferenced(self) -> CleanupResponse:
        """Delete all unreferenced managed image files. Returns count + errors."""
        if not self._assets_dir.exists() and not self._import_batches_dir.exists():
            raise FileNotFoundError(f"Asset folders do not exist: {self._assets_dir}")

        ref_set, reference_scan_available = self._build_reference_set()
        if not reference_scan_available:
            return CleanupResponse(errors=["Reference database unavailable; cleanup was not performed."])
        deleted = 0
        freed = 0
        errors: list[str] = []

        for entry, rel_path, source in self._iter_asset_files():
            if source == "import_batch":
                continue
            if self._reference_ids(entry, rel_path, ref_set, source):
                continue

            if not self._is_safe_to_delete(entry):
                errors.append(f"Safety check blocked: {entry}")
                continue

            try:
                size = entry.stat().st_size
                entry.unlink()
                deleted += 1
                freed += size
                logger.info("Deleted unreferenced asset: %s", entry)
            except OSError as exc:
                errors.append(f"Delete failed {entry}: {exc}")

        self._scan_cache = None
        self._analysis_cache.clear()
        return CleanupResponse(deleted_count=deleted, freed_bytes=freed, errors=errors)

    def delete_single(self, filename: str) -> DeleteAssetResponse:
        """Delete a single managed image file, only if unreferenced."""
        actual_path = self._resolve_asset_identifier(filename)

        if actual_path is None:
            return DeleteAssetResponse(success=False, message=f"File not found: {filename}")

        if not self._is_safe_to_delete(actual_path):
            return DeleteAssetResponse(success=False, message="Safety check blocked: file is outside managed asset folders")

        ref_set, reference_scan_available = self._build_reference_set()
        if not reference_scan_available:
            return DeleteAssetResponse(success=False, message="Reference database unavailable; deletion was blocked.")
        rel_path = self._relative_asset_path(actual_path)
        source = "import_batch" if self._is_under(actual_path, self._import_batches_dir) else "question_bank"
        if source == "import_batch":
            return DeleteAssetResponse(
                success=False,
                message="Import cache files must be managed at batch level to protect review work.",
            )

        if self._reference_ids(actual_path, rel_path, ref_set, source):
            return DeleteAssetResponse(
                success=False,
                message="This asset is still referenced by questions and cannot be deleted.",
            )

        try:
            actual_path.unlink()
            self._scan_cache = None
            self._analysis_cache.clear()
            return DeleteAssetResponse(success=True, message=f"Deleted {actual_path.name}")
        except OSError as exc:
            return DeleteAssetResponse(success=False, message=f"Delete failed: {exc}")

    def _iter_asset_files(self) -> list[tuple[Path, str, str]]:
        """Return supported images from the formal asset library and import batches."""
        items: list[tuple[Path, str, str]] = []
        seen: set[Path] = set()

        def add(entry: Path, rel_path: str, source: str) -> None:
            if not entry.is_file() or entry.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                return
            resolved = entry.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            items.append((entry, rel_path.replace("\\", "/"), source))

        if self._assets_dir.exists() and self._assets_dir.is_dir():
            for entry in sorted(self._assets_dir.rglob("*")):
                try:
                    rel_path = entry.relative_to(self._assets_dir).as_posix()
                except ValueError:
                    rel_path = entry.name
                add(entry, rel_path, "question_bank")

        if self._import_batches_dir.exists() and self._import_batches_dir.is_dir():
            for manifest_path in sorted(self._import_batches_dir.rglob("media_manifest.json")):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    manifest = []
                if not isinstance(manifest, list):
                    continue
                for asset in manifest:
                    if not isinstance(asset, dict):
                        continue
                    rel_path = str(asset.get("relative_path") or "").strip()
                    abs_path = str(asset.get("absolute_path") or "").strip()
                    if not rel_path and not abs_path:
                        continue
                    entry = Path(abs_path) if abs_path else (_PROJECT_ROOT / rel_path)
                    add(entry, rel_path or self._relative_asset_path(entry), "import_batch")

            for entry in sorted(self._import_batches_dir.rglob("*")):
                try:
                    rel_path = entry.relative_to(_PROJECT_ROOT).as_posix()
                except ValueError:
                    try:
                        rel_path = f"data/import-batches/{entry.relative_to(self._import_batches_dir).as_posix()}"
                    except ValueError:
                        rel_path = entry.name
                add(entry, rel_path, "import_batch")

        return items

    def _relative_asset_path(self, path: Path) -> str:
        if self._is_under(path, self._assets_dir):
            return path.relative_to(self._assets_dir).as_posix()
        if self._is_under(path, _PROJECT_ROOT):
            return path.relative_to(_PROJECT_ROOT).as_posix()
        return path.name

    def _resolve_asset_identifier(self, identifier: str) -> Path | None:
        value = identifier.replace("\\", "/").lstrip("/")
        candidates: list[Path] = []

        if value.startswith("data/assets/questions/") or value.startswith("data/import-batches/"):
            candidates.append(_PROJECT_ROOT / value)
        elif "/" in value:
            candidates.append(self._assets_dir / value)
            candidates.append(_PROJECT_ROOT / value)
        else:
            if self._assets_dir.exists():
                candidates.extend(self._assets_dir.rglob(value))
            if self._import_batches_dir.exists():
                candidates.extend(self._import_batches_dir.rglob(value))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Reference detection
    # ------------------------------------------------------------------

    def _build_reference_set(self) -> tuple[dict[str, set[str]], bool]:
        """Build a mapping of {referenced_path → set of question_ids} from the DB.

        Returns an empty dict if the database is unavailable.
        """
        if self._db_path is None or not self._db_path.exists():
            logger.warning("Database not found, reference set is empty")
            return {}, False

        ref_map: dict[str, set[str]] = {}

        try:
            with closing(connect_db(self._db_path, writable=False)) as conn:
                # Source 1: image_assets.file_path
                try:
                    rows = conn.execute(
                        """
                        SELECT file_path, question_id FROM image_assets
                        WHERE file_path IS NOT NULL AND file_path != ''
                          AND question_id IS NOT NULL AND question_id != ''
                        """
                    ).fetchall()
                    for row in rows:
                        path = str(row["file_path"]).strip()
                        question_id = str(row["question_id"]).strip()
                        if path and question_id:
                            ref_map.setdefault(self._normalize_ref_path(path), set()).add(question_id)
                except sqlite3.OperationalError:
                    pass

                # Source 2: question_assets join image_assets
                try:
                    rows = conn.execute(
                        """
                        SELECT ia.file_path, qa.question_id
                        FROM question_assets qa
                        INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
                        WHERE ia.file_path IS NOT NULL AND ia.file_path != ''
                        """
                    ).fetchall()
                    for row in rows:
                        path = str(row["file_path"]).strip()
                        question_id = str(row["question_id"]).strip()
                        if path and question_id:
                            ref_map.setdefault(self._normalize_ref_path(path), set()).add(question_id)
                except sqlite3.OperationalError:
                    pass

                # Source 3: full figure paths stored as JSON in question_text_index.
                try:
                    rows = conn.execute(
                        """
                        SELECT question_id, figures_json FROM question_text_index
                        WHERE figures_json IS NOT NULL AND figures_json != ''
                        """
                    ).fetchall()
                    for row in rows:
                        try:
                            question_id = str(row["question_id"]).strip()
                            figures = json.loads(row["figures_json"])
                            if isinstance(figures, list):
                                for fig in figures:
                                    if not isinstance(fig, dict):
                                        continue
                                    for key in ("local_path", "file_path", "relative_path", "filename"):
                                        path_value = str(fig.get(key) or "").strip()
                                        if path_value and question_id:
                                            ref_map.setdefault(self._normalize_ref_path(path_value), set()).add(question_id)
                        except (json.JSONDecodeError, TypeError):
                            pass
                except sqlite3.OperationalError:
                    pass
                # Source 3: questions table — figures stored as JSON in question_text_index
                try:
                    rows = conn.execute(
                        """
                        SELECT question_id, image_filenames_json FROM question_text_index
                        WHERE image_filenames_json IS NOT NULL AND image_filenames_json != ''
                        """
                    ).fetchall()
                    for row in rows:
                        try:
                            question_id = str(row["question_id"]).strip()
                            filenames = json.loads(row["image_filenames_json"])
                            if isinstance(filenames, list):
                                for f in filenames:
                                    path = str(f).strip()
                                    if path and question_id:
                                        ref_map.setdefault(self._normalize_ref_path(path), set()).add(question_id)
                        except (json.JSONDecodeError, TypeError):
                            pass
                except sqlite3.OperationalError:
                    pass

                # Source 4: questions with figures in review/draft — not in DB yet, skip

        except sqlite3.Error as exc:
            logger.warning("Database error during reference scan: %s", exc)
            return {}, False

        return ref_map, True

    def _reference_ids(
        self,
        entry: Path,
        rel_path: str,
        ref_set: dict[str, set[str]],
        source: str = "question_bank",
    ) -> set[str]:
        """Count how many questions reference this asset file.

        Checks multiple path forms to handle different storage conventions.
        """
        reference_ids: set[str] = set()

        candidates = {self._normalize_ref_path(rel_path)}
        if source == "question_bank":
            candidates.add(self._normalize_ref_path(entry.name))
            candidates.add(self._normalize_ref_path(f"data/assets/questions/{rel_path}"))

        for candidate in candidates:
            if candidate in ref_set:
                reference_ids.update(ref_set[candidate])

        for ref_path, refs in ref_set.items():
            normalized_ref = self._normalize_ref_path(ref_path)
            if normalized_ref in candidates:
                continue
            if any(normalized_ref.endswith("/" + candidate) for candidate in candidates if "/" in candidate):
                reference_ids.update(refs)

        return reference_ids

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _is_safe_to_delete(self, path: Path) -> bool:
        """Ensure the file is within a managed image directory."""
        return self._is_under(path, self._assets_dir) or self._is_under(path, self._import_batches_dir)

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _normalize_ref_path(path: str) -> str:
        value = str(path or "").strip().replace("\\", "/").lstrip("/")
        if value.startswith("files/"):
            value = value[len("files/"):]
        return value
