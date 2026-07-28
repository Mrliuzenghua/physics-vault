"""Business logic for favorite groups and star ratings."""

from __future__ import annotations

from ..repositories.favorites import FavoritesRepository
from ..schemas.favorites import (
    BatchFavoriteResponse,
    BatchStarRequest,
    FavoriteAssignRequest,
    FavoriteGroupCreate,
    FavoriteGroupItem,
    FavoriteGroupUpdate,
    FavoriteItemView,
)


class FavoritesService:
    """Manages favorite groups and per-question star ratings."""

    def __init__(self, repository: FavoritesRepository | None = None) -> None:
        self._repo = repository or FavoritesRepository()

    # ── Groups ────────────────────────────────────────────────────

    def list_groups(self) -> list[FavoriteGroupItem]:
        return [
            FavoriteGroupItem(
                id=r["id"],
                name=r["name"],
                question_count=r.get("question_count", 0),
                sort_order=r.get("sort_order", 0),
                created_at=r.get("created_at", ""),
            )
            for r in self._repo.list_groups()
        ]

    def create_group(self, req: FavoriteGroupCreate) -> FavoriteGroupItem:
        r = self._repo.create_group(req.name)
        return FavoriteGroupItem(**r)

    def update_group(self, group_id: str, req: FavoriteGroupUpdate) -> bool:
        return self._repo.update_group(group_id, req.name)

    def delete_group(self, group_id: str) -> bool:
        return self._repo.delete_group(group_id)

    # ── Assign ────────────────────────────────────────────────────

    def assign(self, req: FavoriteAssignRequest) -> BatchFavoriteResponse:
        result = self._repo.batch_assign(
            req.question_ids, req.group_id, req.star_rating
        )
        return BatchFavoriteResponse(**result)

    def batch_star(self, req: BatchStarRequest) -> BatchFavoriteResponse:
        result = self._repo.batch_assign(
            req.question_ids, group_id=None, star_rating=req.star_rating
        )
        return BatchFavoriteResponse(**result)

    def remove(self, question_ids: list[str]) -> int:
        return self._repo.remove(question_ids)

    # ── Query ─────────────────────────────────────────────────────

    def get_item(self, question_id: str) -> FavoriteItemView | None:
        r = self._repo.get_item(question_id)
        if r is None:
            return None
        return FavoriteItemView(
            question_id=r["question_id"],
            group_id=r.get("group_id"),
            group_name=r.get("group_name"),
            star_rating=r.get("star_rating", 0),
            added_at=r.get("added_at", ""),
        )

    def list_favorites(
        self,
        group_id: str | None = None,
        min_star: int = 0,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[FavoriteItemView], int]:
        rows, total = self._repo.get_favorites(
            group_id=group_id, min_star=min_star, limit=limit, offset=offset
        )
        items = [
            FavoriteItemView(
                question_id=r["question_id"],
                group_id=r.get("group_id"),
                group_name=r.get("group_name"),
                star_rating=r.get("star_rating", 0),
                added_at=r.get("added_at", ""),
            )
            for r in rows
        ]
        return items, total

    def get_favorite_ids(self) -> set[str]:
        return self._repo.get_favorite_ids()
