"""Business logic for collection management and batch question moving."""

from __future__ import annotations

import logging

from ..repositories.collections import CollectionsRepository
from ..schemas.collections import (
    BatchMoveItemResult,
    BatchMoveResponse,
    CollectionNode,
    CreateCollectionRequest,
    CreateCollectionResponse,
)

logger = logging.getLogger(__name__)


class CollectionsService:
    """Manages collections and question-collection mappings."""

    def __init__(self, repository: CollectionsRepository | None = None) -> None:
        self._repo = repository or CollectionsRepository()

    # ── Tree ──────────────────────────────────────────────────────

    def get_tree(self) -> list[CollectionNode]:
        """Return the full collection tree."""
        rows = self._repo.list_all()
        nodes = [
            CollectionNode(
                id=r["id"],
                name=r["name"],
                parent_id=r.get("parent_id"),
                type=r.get("type", "directory"),
                question_count=r.get("question_count", 0),
                created_at=r.get("created_at", ""),
                updated_at=r.get("updated_at", ""),
            )
            for r in rows
        ]
        return _build_tree(nodes)

    # ── Create ────────────────────────────────────────────────────

    def create(self, request: CreateCollectionRequest) -> CreateCollectionResponse:
        # Validate parent if specified
        if request.parent_id:
            parent = self._repo.get(request.parent_id)
            if parent is None:
                raise ValueError(f"父级目录不存在: {request.parent_id}")

        result = self._repo.create(
            name=request.name,
            parent_id=request.parent_id,
            ctype=request.type,
        )
        return CreateCollectionResponse(**result)

    # ── Batch move ────────────────────────────────────────────────

    def batch_move(self, question_ids: list[str], target_id: str) -> BatchMoveResponse:
        # Validate target exists
        target = self._repo.get(target_id)
        if target is None:
            raise ValueError(f"目标目录不存在: {target_id}")

        result = self._repo.add_questions(target_id, question_ids)

        items = [
            BatchMoveItemResult(**r) for r in result["results"]
        ]

        return BatchMoveResponse(
            total=result["total"],
            success_count=result["success_count"],
            skipped_count=result["skipped_count"],
            failed_count=result["failed_count"],
            results=items,
        )

    # ── Remove ────────────────────────────────────────────────────

    def remove_from_collection(
        self, question_ids: list[str], collection_id: str
    ) -> int:
        return self._repo.remove_questions(collection_id, question_ids)

    # ── Get collections for a question ────────────────────────────

    def get_for_question(self, question_id: str) -> list[CollectionNode]:
        rows = self._repo.get_collections_for_question(question_id)
        return [
            CollectionNode(
                id=r["id"],
                name=r["name"],
                parent_id=r.get("parent_id"),
                type=r.get("type", "directory"),
            )
            for r in rows
        ]


def _build_tree(nodes: list[CollectionNode]) -> list[CollectionNode]:
    """Build a nested tree from a flat list of nodes."""
    by_id: dict[str, CollectionNode] = {n.id: n for n in nodes}
    roots: list[CollectionNode] = []

    for node in nodes:
        if node.parent_id and node.parent_id in by_id:
            by_id[node.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots
