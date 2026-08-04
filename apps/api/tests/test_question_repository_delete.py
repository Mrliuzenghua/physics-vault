import sqlite3
from pathlib import Path
from uuid import uuid4

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_search import (
    QuestionDatabaseUnavailableError,
    QuestionSearchRepository,
)
from physics_vault_api.repositories.question_write import QuestionWriteRepository
from physics_vault_api.services.question_write import QuestionWriteService


def _temp_db() -> Path:
    path = Path(".codex-run") / f"question-delete-{uuid4().hex}.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _save_question(db_path: Path, question_id: str = "q-delete") -> None:
    service = QuestionWriteService(QuestionWriteRepository(str(db_path)))
    result = service.save_batch([
        {
            "question_id": question_id,
            "question_type": "single_choice",
            "title": "A test question",
            "options": [{"opt": "A", "content": "test"}],
            "answer": "A",
            "analysis": "analysis",
            "difficulty": 2,
        }
    ])
    assert result.saved_count == 1


def test_search_repository_recovers_when_database_becomes_available() -> None:
    db_path = _temp_db()
    repo = QuestionSearchRepository(str(db_path))
    try:
        repo.search_questions(limit=10)
    except QuestionDatabaseUnavailableError:
        pass
    else:
        raise AssertionError("missing databases must not silently return demo questions")

    initialize_database(db_path)
    _save_question(db_path, "q-live")

    rows, total = repo.search_questions(limit=10)

    assert total == 1
    assert rows[0]["question_id"] == "q-live"


def test_delete_many_removes_question_bindings_and_soft_references() -> None:
    db_path = initialize_database(_temp_db())
    _save_question(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("INSERT INTO favorite_items (question_id, star_rating) VALUES (?, 3)", ("q-delete",))
    conn.execute(
        "INSERT INTO collections (id, name, type) VALUES ('c1', 'Collection', 'directory')"
    )
    conn.execute(
        "INSERT INTO collection_questions (collection_id, question_id) VALUES ('c1', ?)",
        ("q-delete",),
    )
    conn.execute(
        """
        INSERT INTO image_assets (asset_id, filename, file_path, question_id)
        VALUES ('asset-1', 'a.png', 'a.png', ?)
        """,
        ("q-delete",),
    )
    conn.execute(
        "INSERT INTO question_assets (link_id, question_id, asset_id) VALUES ('l1', ?, 'asset-1')",
        ("q-delete",),
    )
    conn.execute(
        """
        INSERT INTO embeddings (
            embedding_id, owner_type, owner_id, vector_type,
            model_name, dimensions, vector_json
        ) VALUES ('e1', 'question', ?, 'stem', 'test', 3, '[0,0,0]')
        """,
        ("q-delete",),
    )
    conn.commit()
    conn.close()

    result = QuestionWriteRepository(str(db_path)).delete_many(["q-delete"])

    assert result["deleted"] == 1
    conn = sqlite3.connect(db_path)
    checks = {
        "questions": "SELECT COUNT(*) FROM questions WHERE question_id = 'q-delete'",
        "question_text_index": "SELECT COUNT(*) FROM question_text_index WHERE question_id = 'q-delete'",
        "question_search_fts": "SELECT COUNT(*) FROM question_search_fts WHERE question_id = 'q-delete'",
        "favorite_items": "SELECT COUNT(*) FROM favorite_items WHERE question_id = 'q-delete'",
        "collection_questions": "SELECT COUNT(*) FROM collection_questions WHERE question_id = 'q-delete'",
        "question_assets": "SELECT COUNT(*) FROM question_assets WHERE question_id = 'q-delete'",
        "embeddings": "SELECT COUNT(*) FROM embeddings WHERE owner_id = 'q-delete'",
    }
    for table, sql in checks.items():
        assert conn.execute(sql).fetchone()[0] == 0, table
    assert conn.execute(
        "SELECT question_id FROM image_assets WHERE asset_id = 'asset-1'"
    ).fetchone()[0] is None
    conn.close()
