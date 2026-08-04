"""Explicit compatibility boundary for endpoints not migrated from ``legacy_app`` yet."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter
from fastapi.routing import BaseRoute

from .legacy_app import app as legacy_app

RouteKey = tuple[str, str]

# Every route in this set needs an explicit migration or removal decision. Keeping the
# manifest here prevents legacy_app from silently expanding the public API surface.
LEGACY_COMPAT_ROUTE_KEYS: frozenset[RouteKey] = frozenset(
    {
        ("/", "GET"),
        ("/embeddings/questions/build", "POST"),
        ("/embeddings/status", "GET"),
        ("/images", "GET"),
        ("/knowledge-points", "GET"),
        ("/knowledge-points/counts", "GET"),
        ("/papers", "GET"),
        ("/papers/{paper_id}", "GET"),
        ("/papers/{paper_id}/questions", "GET"),
        ("/processing-runs", "GET"),
        ("/questions/import", "POST"),
        ("/questions/{question_id}", "GET"),
        ("/questions/{question_id}", "PUT"),
        ("/questions/{question_id}/assets", "GET"),
        ("/questions/{question_id}/knowledge-points", "GET"),
        ("/questions/{question_id}/knowledge-points", "PUT"),
        ("/questions/{question_id}/knowledge-points/{rank}", "DELETE"),
        ("/questions/{question_id}/knowledge-points/{rank}", "PUT"),
        ("/questions/{question_id}/propose-fix", "POST"),
        ("/questions/{question_id}/report-issue", "POST"),
        ("/questions/{question_id}/review", "POST"),
        ("/questions/{question_id}/review-history", "GET"),
        ("/questions/{question_id}/versions", "GET"),
        ("/questions/{question_id}/versions/{version_id}", "GET"),
        ("/questions/{question_id}/versions/{version_id}/rollback", "POST"),
        ("/review-queue/pending-fixes", "GET"),
        ("/review-queue/rejected", "GET"),
        ("/review-queue/{review_id}", "GET"),
        ("/review-queue/{review_id}/decide", "POST"),
        ("/stats/questions", "GET"),
    }
)


def route_method_keys(route: BaseRoute) -> frozenset[RouteKey]:
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None) or ()
    if not path:
        return frozenset()
    return frozenset((path, method) for method in methods)


def collect_route_method_keys(routes: Iterable[BaseRoute]) -> set[RouteKey]:
    keys: set[RouteKey] = set()
    for route in routes:
        keys.update(route_method_keys(route))
    return keys


def build_legacy_compat_router() -> APIRouter:
    selected: list[BaseRoute] = []
    selected_keys: set[RouteKey] = set()

    for route in legacy_app.routes:
        matching_keys = route_method_keys(route) & LEGACY_COMPAT_ROUTE_KEYS
        if not matching_keys:
            continue
        if route_method_keys(route) != matching_keys:
            raise RuntimeError(f"Legacy route mixes allowed and unlisted methods: {route.path}")
        duplicate_keys = selected_keys & matching_keys
        if duplicate_keys:
            raise RuntimeError(f"Duplicate legacy compatibility routes: {sorted(duplicate_keys)}")
        selected.append(route)
        selected_keys.update(matching_keys)

    missing_keys = LEGACY_COMPAT_ROUTE_KEYS - selected_keys
    if missing_keys:
        raise RuntimeError(f"Legacy compatibility routes are missing: {sorted(missing_keys)}")

    router = APIRouter()
    router.routes.extend(selected)
    return router


__all__ = [
    "LEGACY_COMPAT_ROUTE_KEYS",
    "build_legacy_compat_router",
    "collect_route_method_keys",
    "route_method_keys",
]
