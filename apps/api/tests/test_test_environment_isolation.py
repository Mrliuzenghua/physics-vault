from __future__ import annotations

import os

from conftest import TEST_DB_PATH, TEST_REVIEW_DB_PATH


def test_pytest_databases_are_isolated_to_the_current_process() -> None:
    process_suffix = f"_{os.getpid()}.sqlite3"

    if not os.getenv("PHYSICS_TEST_DB_PATH"):
        assert TEST_DB_PATH.name.endswith(process_suffix)
    if not os.getenv("PHYSICS_TEST_REVIEW_DB_PATH"):
        assert TEST_REVIEW_DB_PATH.name.endswith(process_suffix)
    assert TEST_DB_PATH != TEST_REVIEW_DB_PATH
    assert os.environ["PHYSICS_DB_PATH"] == str(TEST_DB_PATH)
    assert os.environ["PHYSICS_REVIEW_DB_PATH"] == str(TEST_REVIEW_DB_PATH)
