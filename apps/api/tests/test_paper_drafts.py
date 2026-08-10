from pathlib import Path

import pytest

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.paper_drafts import (
    PaperDraftConflictError,
    PaperDraftRepository,
)
from physics_vault_api.schemas.paper_drafts import (
    PaperDraftItem,
    PaperDraftUpsertRequest,
)
from physics_vault_api.services.paper_drafts import PaperDraftService


def _service(tmp_path: Path) -> PaperDraftService:
    db_path = initialize_database(tmp_path / "paper-drafts.sqlite3")
    return PaperDraftService(PaperDraftRepository(str(db_path)))


def _request(
    *,
    base_updated_at: str | None = None,
    title: str = "Physics paper",
    item_id: str = "question-1",
) -> PaperDraftUpsertRequest:
    return PaperDraftUpsertRequest(
        id="draft-1",
        base_updated_at=base_updated_at,
        title=title,
        items=[
            PaperDraftItem(
                id=item_id,
                type="text",
                title=title,
                position=0,
            )
        ],
    )


def test_stale_paper_draft_save_cannot_overwrite_newer_content(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.save(_request())
    second = service.save(
        _request(base_updated_at=first.updated_at, title="AI enriched", item_id="knowledge-1")
    )

    with pytest.raises(PaperDraftConflictError):
        service.save(
            _request(base_updated_at=first.updated_at, title="Stale browser save")
        )

    current = service.get("draft-1")
    assert current.updated_at == second.updated_at
    assert current.title == "AI enriched"
    assert [item.id for item in current.items] == ["knowledge-1"]


def test_project_question_snapshot_round_trips_in_draft_payload(tmp_path: Path) -> None:
    service = _service(tmp_path)
    request = PaperDraftUpsertRequest(
        id="draft-snapshot",
        title="Editable project question",
        items=[
            PaperDraftItem(
                id="question-instance-1",
                type="question",
                title="项目内修改后的题干",
                payload={
                    "question_snapshot": {
                        "question_id": "bank-question-1",
                        "title": "项目内修改后的题干",
                        "options": [{"opt": "A", "content": "项目内选项"}],
                        "answer": "A",
                        "analysis": "项目内解析",
                        "figures": [],
                    }
                },
            )
        ],
    )

    saved = service.save(request)

    snapshot = saved.items[0].payload["question_snapshot"]
    assert snapshot["title"] == "项目内修改后的题干"
    assert snapshot["options"][0]["content"] == "项目内选项"
    assert snapshot["analysis"] == "项目内解析"
