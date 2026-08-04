from pathlib import Path
from uuid import uuid4

import pytest

from physics_vault_api.repositories.review_drafts import (
    ReviewDraftConflictError,
    SQLiteReviewDraftRepository,
)


def _repository(history_limit: int = 30) -> SQLiteReviewDraftRepository:
    db_path = Path(".codex-run") / f"review-drafts-{uuid4().hex}.sqlite3"
    return SQLiteReviewDraftRepository(str(db_path), history_limit=history_limit)


def _state(title: str) -> dict:
    return {
        "drafts": [{"question_id": "draft-1", "title": title}],
        "knowledge_drafts": [],
        "task_meta": {"warnings": []},
        "current_index": 0,
        "queue": "risk",
    }


def test_review_draft_save_increments_version_and_persists_history():
    repository = _repository()

    first = repository.save("task-1", 0, _state("第一版"))
    second = repository.save("task-1", first.version, _state("第二版"))

    assert first.version == 1
    assert second.version == 2
    assert repository.get("task-1").state["drafts"][0]["title"] == "第二版"
    assert [item.version for item in repository.list_versions("task-1")] == [2, 1]


def test_review_draft_rejects_stale_base_version_without_overwriting():
    repository = _repository()
    first = repository.save("task-1", 0, _state("服务器版本"))

    with pytest.raises(ReviewDraftConflictError) as exc_info:
        repository.save("task-1", 0, _state("过期页面版本"))

    assert exc_info.value.current.version == first.version
    assert repository.get("task-1").state["drafts"][0]["title"] == "服务器版本"


def test_review_draft_restore_creates_a_new_version():
    repository = _repository()
    first = repository.save("task-1", 0, _state("第一版"))
    second = repository.save("task-1", first.version, _state("第二版"))

    restored = repository.restore("task-1", first.version, second.version)

    assert restored is not None
    assert restored.version == 3
    assert restored.state["drafts"][0]["title"] == "第一版"
    assert [item.version for item in repository.list_versions("task-1")] == [3, 2, 1]


def test_review_draft_history_is_bounded():
    repository = _repository(history_limit=5)
    version = 0
    for index in range(7):
        version = repository.save("task-1", version, _state(f"第 {index + 1} 版")).version

    assert [item.version for item in repository.list_versions("task-1", limit=20)] == [7, 6, 5, 4, 3]
