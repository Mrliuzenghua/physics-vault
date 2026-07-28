from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_SRC = PROJECT_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from physics_vault_api.db_schema import initialize_database, reset_database  # noqa: E402
from physics_vault_api.paths import default_db_path  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset Physics Vault SQLite database to the standard empty schema.",
    )
    parser.add_argument(
        "--db-path",
        default=str(default_db_path()),
        help="Target sqlite file path. Defaults to project data/app-db/physics_vault.sqlite3",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a backup before resetting the database.",
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only create the schema if missing; do not delete existing data.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db_path)

    if args.init_only:
        resolved = initialize_database(db_path)
        print(f"initialized: {resolved}")
        return 0

    resolved, backup_path = reset_database(db_path, backup=not args.no_backup)
    print(f"reset: {resolved}")
    if backup_path:
        print(f"backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
