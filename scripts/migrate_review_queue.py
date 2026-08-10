"""Preview or explicitly migrate legacy review_queue rows into the review workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from physics_vault_api.repositories.review_queue import ReviewQueueRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Copy verified legacy rows into the review workspace")
    parser.add_argument(
        "--delete-legacy",
        action="store_true",
        help="Delete legacy rows only after a conflict-free migration; requires --apply",
    )
    args = parser.parse_args()
    if args.delete_legacy and not args.apply:
        parser.error("--delete-legacy requires --apply")

    repository = ReviewQueueRepository(migrate_legacy=False, initialize=args.apply)
    result = (
        repository.apply_legacy_migration(delete_legacy_after_migrate=args.delete_legacy)
        if args.apply
        else repository.preview_legacy_migration()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("conflict_count") else 2


if __name__ == "__main__":
    raise SystemExit(main())
