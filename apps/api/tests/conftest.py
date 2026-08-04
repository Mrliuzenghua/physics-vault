from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = API_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

TEST_DB_PATH = Path(tempfile.gettempdir()) / "physics_vault_api_tests.sqlite3"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ.setdefault("PHYSICS_DB_PATH", str(TEST_DB_PATH))

TEST_REVIEW_DB_PATH = Path(tempfile.gettempdir()) / "physics_vault_api_review_tests.sqlite3"
if TEST_REVIEW_DB_PATH.exists():
    TEST_REVIEW_DB_PATH.unlink()
os.environ.setdefault("PHYSICS_REVIEW_DB_PATH", str(TEST_REVIEW_DB_PATH))

os.environ.setdefault("PHYSICS_RESTORE_RUNTIME_AI_CONFIG", "false")
