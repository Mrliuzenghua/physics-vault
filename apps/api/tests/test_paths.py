from __future__ import annotations

from pathlib import Path

from physics_vault_api import paths


def test_database_paths_have_distinct_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.delenv("PHYSICS_DB_PATH", raising=False)
    monkeypatch.delenv("PHYSICS_REVIEW_DB_PATH", raising=False)

    assert paths.default_db_path() == tmp_path / "data" / "app-db" / "physics_vault.sqlite3"
    assert paths.default_review_db_path() == tmp_path / "data" / "mcp" / "review_workspace.sqlite3"


def test_relative_configured_paths_are_project_relative(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setenv("PHYSICS_DB_PATH", "var/canonical.sqlite3")
    monkeypatch.setenv("PHYSICS_REVIEW_DB_PATH", "var/review.sqlite3")
    monkeypatch.setenv("PHYSICS_EXPORT_DIR", "var/exports")

    assert paths.default_db_path() == tmp_path / "var" / "canonical.sqlite3"
    assert paths.default_review_db_path() == tmp_path / "var" / "review.sqlite3"
    assert paths.default_exports_dir() == tmp_path / "var" / "exports"


def test_absolute_configured_path_is_preserved(monkeypatch, tmp_path: Path) -> None:
    configured = tmp_path / "external" / "canonical.sqlite3"
    monkeypatch.setenv("PHYSICS_DB_PATH", str(configured))

    assert paths.default_db_path() == configured
