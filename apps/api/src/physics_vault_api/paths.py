from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return project_root() / "data"


def default_db_path() -> Path:
    if configured := os.getenv("PHYSICS_DB_PATH"):
        return Path(configured)
    return data_root() / "app-db" / "physics_vault.sqlite3"


def default_review_db_path() -> Path:
    if configured := os.getenv("PHYSICS_REVIEW_DB_PATH"):
        return Path(configured)
    return data_root() / "mcp" / "review_workspace.sqlite3"


def default_assets_dir() -> Path:
    return data_root() / "assets" / "questions"


def default_backups_dir() -> Path:
    return data_root() / "backups"


def default_import_batches_dir() -> Path:
    return data_root() / "import-batches"


def default_exports_dir() -> Path:
    if configured := os.getenv("PHYSICS_EXPORT_DIR"):
        return Path(configured)
    return data_root() / "exports"
