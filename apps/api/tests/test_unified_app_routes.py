from __future__ import annotations

import warnings

from fastapi import APIRouter, FastAPI

from physics_vault_api.main import (
    _covered_route_keys,
    _iter_concrete_routes,
    _route_key,
    create_app,
)


def test_covered_route_keys_expands_included_router_wrappers() -> None:
    router = APIRouter()

    @router.get("/wrapped")
    def wrapped() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)

    assert ("/wrapped", frozenset({"GET"})) in _covered_route_keys(app.routes)


def test_unified_app_keeps_modular_overlap_routes_unique() -> None:
    app = create_app()
    keys = [_route_key(route) for route in _iter_concrete_routes(app.routes)]

    for route_key in (
        ("/search/questions", frozenset({"GET"})),
        ("/filters/facets", frozenset({"GET"})),
        ("/review-queue", frozenset({"GET"})),
    ):
        assert keys.count(route_key) == 1


def test_unified_openapi_has_no_duplicate_operation_warning() -> None:
    app = create_app()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app.openapi()

    duplicate_warnings = [
        warning
        for warning in caught
        if "Duplicate Operation ID" in str(warning.message)
    ]
    assert duplicate_warnings == []
