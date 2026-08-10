"""Stable local and CI entrypoint for the API-303 contract gate."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from physics_vault_api.contract_gate import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
