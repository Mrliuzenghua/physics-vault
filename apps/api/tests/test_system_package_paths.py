from __future__ import annotations

from pathlib import Path

from physics_vault_api.routers import export_package, restore_package


def test_export_uses_canonical_configured_defaults(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "canonical.sqlite3"
    assets = tmp_path / "assets"
    monkeypatch.setattr(export_package, "default_db_path", lambda: database)
    monkeypatch.setattr(export_package, "default_assets_dir", lambda: assets)

    assert export_package._resolve_export_paths("", "") == (database, assets)


def test_restore_uses_canonical_configured_defaults(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "canonical.sqlite3"
    assets = tmp_path / "assets"
    backups = tmp_path / "backups"
    monkeypatch.setattr(restore_package, "default_db_path", lambda: database)
    monkeypatch.setattr(restore_package, "default_assets_dir", lambda: assets)
    monkeypatch.setattr(restore_package, "default_backups_dir", lambda: backups)

    assert restore_package._resolve_restore_paths(None, None) == (database, assets, backups)


def test_explicit_package_paths_override_database_and_assets(tmp_path: Path) -> None:
    database = tmp_path / "external.sqlite3"
    assets = tmp_path / "external-assets"

    assert export_package._resolve_export_paths(str(database), str(assets)) == (database, assets)
    resolved_db, resolved_assets, _ = restore_package._resolve_restore_paths(str(database), str(assets))
    assert (resolved_db, resolved_assets) == (database, assets)
