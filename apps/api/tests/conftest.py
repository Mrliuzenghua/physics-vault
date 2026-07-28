from __future__ import annotations

import os
import tempfile
from pathlib import Path


TEST_DB_PATH = Path(tempfile.gettempdir()) / "physics_vault_api_tests.sqlite3"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ.setdefault("PHYSICS_DB_PATH", str(TEST_DB_PATH))
os.environ.setdefault("PHYSICS_RESTORE_RUNTIME_AI_CONFIG", "false")
