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
