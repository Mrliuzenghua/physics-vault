from __future__ import annotations

import sqlite3

import pytest

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.review_queue import ReviewQueueRepository


def _seed_legacy_review_queue(canonical_path, *, reason: str = "Needs review") -> None:
    initialize_database(canonical_path)
    with connect_db(canonical_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type) VALUES (?, ?)",
            ("Q-1", "single_choice"),
        )
        connection.execute(
            """
            CREATE TABLE review_queue (
                review_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                queue_type TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                reason TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status,
                priority, reason, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("REV-1", "question", "Q-1", "ai_fix", "pending", 3, reason, "{}", "2026-01-01", "2026-01-01"),
        )
        connection.commit()


def test_review_queue_legacy_migration_previews_applies_and_is_idempotent(tmp_path) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    review_path = tmp_path / "review.sqlite3"
    _seed_legacy_review_queue(canonical_path)
    repository = ReviewQueueRepository(str(review_path), legacy_db_path=str(canonical_path))

    assert repository.preview_legacy_migration() == {
        "source_available": True,
        "source_count": 1,
        "already_migrated_count": 0,
        "pending_count": 1,
        "conflict_count": 0,
    }

    assert repository.apply_legacy_migration() == {
        "source_available": True,
        "source_count": 1,
        "already_migrated_count": 0,
        "pending_count": 1,
        "conflict_count": 0,
        "migrated_count": 1,
        "legacy_deleted": False,
    }
    assert repository.list() == [
        {
            "review_id": "REV-1",
            "entity_type": "question",
            "entity_id": "Q-1",
            "queue_type": "ai_fix",
            "status": "pending",
            "priority": 3,
            "reason": "Needs review",
            "payload_json": "{}",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
    ]
    assert repository.apply_legacy_migration()["migrated_count"] == 0
    assert repository.apply_legacy_migration(delete_legacy_after_migrate=True)["legacy_deleted"] is True
    with connect_db(canonical_path, writable=False) as connection:
        assert connection.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 0


def test_review_queue_migration_preview_does_not_create_the_review_database(tmp_path) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    review_path = tmp_path / "review.sqlite3"
    _seed_legacy_review_queue(canonical_path)

    preview = ReviewQueueRepository(
        str(review_path),
        legacy_db_path=str(canonical_path),
        initialize=False,
    ).preview_legacy_migration()

    assert preview["pending_count"] == 1
    assert review_path.exists() is False


def test_review_queue_legacy_migration_rejects_conflicting_review_ids(tmp_path) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    review_path = tmp_path / "review.sqlite3"
    _seed_legacy_review_queue(canonical_path)
    repository = ReviewQueueRepository(str(review_path), legacy_db_path=str(canonical_path))
    with sqlite3.connect(review_path) as connection:
        connection.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status,
                priority, reason, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("REV-1", "question", "Q-1", "ai_fix", "pending", 3, "Different", "{}", "2026-01-01", "2026-01-01"),
        )
        connection.commit()

    assert repository.preview_legacy_migration()["conflict_count"] == 1
    with pytest.raises(ValueError, match="conflicting review IDs"):
        repository.apply_legacy_migration()
