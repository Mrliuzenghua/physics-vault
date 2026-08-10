from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PIL import Image

from physics_vault_api.services.assets_manager import AssetsManagerService


def _create_reference_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE image_assets (
                asset_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                question_id TEXT
            );
            CREATE TABLE question_assets (
                link_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                asset_id TEXT NOT NULL
            );
            CREATE TABLE question_text_index (
                question_id TEXT PRIMARY KEY,
                figures_json TEXT,
                image_filenames_json TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO image_assets(asset_id, file_path, question_id) VALUES (?, ?, ?)",
            ("asset-1", "data/assets/questions/used.png", "Q-1"),
        )
        conn.execute(
            "INSERT INTO question_assets(link_id, question_id, asset_id) VALUES (?, ?, ?)",
            ("link-1", "Q-1", "asset-1"),
        )
        conn.execute(
            "INSERT INTO question_text_index(question_id, figures_json, image_filenames_json) VALUES (?, ?, ?)",
            ("Q-2", json.dumps([{"local_path": "used.png"}]), json.dumps([])),
        )


def test_asset_list_has_real_references_source_stats_batches_and_pagination(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    import_dir = tmp_path / "import-batches"
    batch_dir = import_dir / "batch_demo" / "media"
    assets_dir.mkdir()
    batch_dir.mkdir(parents=True)
    (assets_dir / "used.png").write_bytes(b"used")
    (assets_dir / "orphan.png").write_bytes(b"orphan-file")
    (batch_dir / "staged.png").write_bytes(b"staged")
    db_path = tmp_path / "test.sqlite3"
    _create_reference_db(db_path)

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(db_path),
        import_batches_dir=str(import_dir),
    )
    response = service.get_asset_list(source="question_bank", page=1, page_size=1, sort_by="name")

    assert response.reference_scan_available is True
    assert response.stats.total == 2
    assert response.stats.total_size_bytes == len(b"used") + len(b"orphan-file")
    assert response.library_stats.total == 3
    assert response.pagination.total_items == 2
    assert response.pagination.total_pages == 2
    assert len(response.assets) == 1
    assert response.batches[0].batch_id == "batch_demo"
    assert response.batches[0].asset_count == 1

    used = service.get_asset_list(source="question_bank", filter_mode="referenced").assets[0]
    assert used.reference_count == 2
    assert used.reference_question_ids == ["Q-1", "Q-2"]
    assert used.lifecycle_status == "referenced"

    staged = service.get_asset_list(source="import_batch").assets[0]
    assert staged.batch_id == "batch_demo"
    assert staged.lifecycle_status == "staged"


def test_asset_list_matches_absolute_reference_paths(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    nested_dir = assets_dir / "nested"
    nested_dir.mkdir(parents=True)
    asset = nested_dir / "used.png"
    asset.write_bytes(b"used")
    db_path = tmp_path / "test.sqlite3"
    _create_reference_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO image_assets(asset_id, file_path, question_id) VALUES (?, ?, ?)",
            ("asset-absolute", str(asset), "Q-absolute"),
        )

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(db_path),
        import_batches_dir=str(tmp_path / "import-batches"),
    )

    result = service.get_asset_list(source="question_bank")

    assert result.assets[0].is_referenced is True
    assert "Q-absolute" in result.assets[0].reference_question_ids


def test_cleanup_preview_blocks_when_reference_database_is_missing(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "unknown.png").write_bytes(b"unknown")

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(tmp_path / "missing.sqlite3"),
        import_batches_dir=str(tmp_path / "missing-imports"),
    )

    response = service.get_asset_list(source="question_bank")
    assert response.reference_scan_available is False
    assert response.assets[0].lifecycle_status == "unknown"
    assert response.stats.unreferenced == 0
    preview = service.get_cleanup_preview()
    assert preview.candidate_count == 0
    assert preview.protected_count == 1
    assert service.cleanup_unreferenced().deleted_count == 0
    assert (assets_dir / "unknown.png").exists()


def test_storage_analysis_reports_exact_duplicates_without_mutation(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    first = assets_dir / "first.png"
    Image.new("RGB", (8, 8), "white").save(first)
    second = assets_dir / "second.png"
    second.write_bytes(first.read_bytes())

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(tmp_path / "missing.sqlite3"),
        import_batches_dir=str(tmp_path / "missing-imports"),
    )
    result = service.analyze_storage(source="question_bank")

    assert result.scanned_files == 2
    assert result.duplicate_groups == 1
    assert result.duplicate_files == 1
    assert result.reclaimable_bytes == first.stat().st_size
    assert first.exists() and second.exists()


def test_import_cache_cleanup_skips_active_batches_and_deletes_inactive_images(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    import_dir = tmp_path / "import-batches"
    idle_dir = import_dir / "batch_idle" / "media"
    active_dir = import_dir / "batch_active" / "media"
    assets_dir.mkdir()
    idle_dir.mkdir(parents=True)
    active_dir.mkdir(parents=True)
    (import_dir / "batch_idle" / "status.json").write_text('{"status":"completed"}', encoding="utf-8")
    (import_dir / "batch_active" / "status.json").write_text('{"status":"running"}', encoding="utf-8")
    idle_image = idle_dir / "idle.png"
    active_image = active_dir / "active.png"
    Image.new("RGB", (8, 8), "white").save(idle_image)
    Image.new("RGB", (8, 8), "black").save(active_image)
    db_path = tmp_path / "test.sqlite3"
    _create_reference_db(db_path)

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(db_path),
        import_batches_dir=str(import_dir),
    )
    preview = service.get_import_cache_cleanup_preview()

    assert preview.batch_count == 1
    assert preview.candidate_count == 1
    assert preview.protected_count == 1
    assert preview.active_batches == ["batch_active"]

    result = service.cleanup_import_cache()
    assert result.deleted_count == 1
    assert not idle_image.exists()
    assert active_image.exists()
    assert (import_dir / "batch_idle" / "status.json").exists()


def test_business_collections_follow_reference_status_not_storage_folder(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    import_dir = tmp_path / "import-batches"
    batch_dir = import_dir / "batch_demo" / "media"
    assets_dir.mkdir()
    batch_dir.mkdir(parents=True)
    (assets_dir / "used.png").write_bytes(b"used")
    (assets_dir / "unused-local.png").write_bytes(b"unused-local")
    (batch_dir / "used-import.png").write_bytes(b"used-import")
    (batch_dir / "unused-import.png").write_bytes(b"unused-import")
    db_path = tmp_path / "test.sqlite3"
    _create_reference_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO image_assets(asset_id, file_path, question_id) VALUES (?, ?, ?)",
            (
                "asset-import",
                "data/import-batches/batch_demo/media/used-import.png",
                "Q-3",
            ),
        )

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(db_path),
        import_batches_dir=str(import_dir),
    )

    library = service.get_asset_list(source="all", filter_mode="referenced", page_size=20)
    cache = service.get_asset_list(source="all", filter_mode="unreferenced", page_size=20)

    assert {asset.filename for asset in library.assets} == {"used.png", "used-import.png"}
    assert {asset.filename for asset in cache.assets} == {"unused-local.png", "unused-import.png"}
    assert all(asset.is_referenced for asset in library.assets)
    assert all(not asset.is_referenced for asset in cache.assets)


def test_unused_cache_can_be_deleted_but_referenced_assets_are_protected(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    import_dir = tmp_path / "import-batches"
    batch_dir = import_dir / "batch_idle" / "media"
    assets_dir.mkdir()
    batch_dir.mkdir(parents=True)
    (import_dir / "batch_idle" / "status.json").write_text('{"status":"completed"}', encoding="utf-8")
    referenced = assets_dir / "used.png"
    unused_local = assets_dir / "unused-local.png"
    unused_import = batch_dir / "unused-import.png"
    referenced.write_bytes(b"used")
    unused_local.write_bytes(b"unused-local")
    unused_import.write_bytes(b"unused-import")
    db_path = tmp_path / "test.sqlite3"
    _create_reference_db(db_path)

    service = AssetsManagerService(
        assets_dir=str(assets_dir),
        db_path=str(db_path),
        import_batches_dir=str(import_dir),
    )

    protected_result = service.delete_single("used.png")
    assert protected_result.success is False
    assert referenced.exists()

    delete_result = service.delete_single("data/import-batches/batch_idle/media/unused-import.png")
    assert delete_result.success is True
    assert not unused_import.exists()

    preview = service.get_unused_cache_cleanup_preview()
    assert preview.candidate_count == 1
    cleanup = service.cleanup_unused_cache()
    assert cleanup.deleted_count == 1
    assert not unused_local.exists()
    assert referenced.exists()
