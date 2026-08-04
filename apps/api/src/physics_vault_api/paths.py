from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return project_root() / "data"


def _configured_path(env_name: str, default: Path) -> Path:
    configured = os.getenv(env_name, "").strip()
    if not configured:
        return default
    path = Path(configured).expanduser()
    return path if path.is_absolute() else project_root() / path


def default_db_path() -> Path:
    return _configured_path(
        "PHYSICS_DB_PATH",
        data_root() / "app-db" / "physics_vault.sqlite3",
    )


def default_review_db_path() -> Path:
    return _configured_path(
        "PHYSICS_REVIEW_DB_PATH",
        data_root() / "mcp" / "review_workspace.sqlite3",
    )


def default_assets_dir() -> Path:
    return data_root() / "assets" / "questions"


def default_backups_dir() -> Path:
    return data_root() / "backups"


def default_import_batches_dir() -> Path:
    return data_root() / "import-batches"


def default_exports_dir() -> Path:
    return _configured_path("PHYSICS_EXPORT_DIR", data_root() / "exports")
