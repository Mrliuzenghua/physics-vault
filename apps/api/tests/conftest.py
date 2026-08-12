from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = API_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _configure_test_database(
    runtime_env: str,
    override_env: str,
    filename_prefix: str,
) -> Path:
    """Give each pytest process its own database unless a test-only path is explicit."""
    override = str(os.getenv(override_env) or "").strip()
    path = (
        Path(override).expanduser().resolve()
        if override
        else Path(tempfile.gettempdir()) / f"{filename_prefix}_{os.getpid()}.sqlite3"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    os.environ[runtime_env] = str(path)
    return path


TEST_DB_PATH = _configure_test_database(
    "PHYSICS_DB_PATH",
    "PHYSICS_TEST_DB_PATH",
    "physics_vault_api_tests",
)
TEST_REVIEW_DB_PATH = _configure_test_database(
    "PHYSICS_REVIEW_DB_PATH",
    "PHYSICS_TEST_REVIEW_DB_PATH",
    "physics_vault_api_review_tests",
)

os.environ.setdefault("PHYSICS_RESTORE_RUNTIME_AI_CONFIG", "false")
