from __future__ import annotations

import warnings

from physics_vault_api.app import create_app
from physics_vault_api.legacy_compat import (
    LEGACY_COMPAT_ROUTE_KEYS,
    build_legacy_compat_router,
    collect_route_method_keys,
)
from physics_vault_api.main import create_app as create_main_app


def test_main_uses_the_single_application_factory() -> None:
    assert create_main_app is create_app


def test_legacy_compatibility_manifest_matches_router() -> None:
    router = build_legacy_compat_router()

    assert collect_route_method_keys(router.routes) == set(LEGACY_COMPAT_ROUTE_KEYS)


def test_unified_app_has_no_duplicate_path_method_pairs() -> None:
    app = create_app()
    keys: list[tuple[str, str]] = []
    for route in app.routes:
        keys.extend(collect_route_method_keys([route]))

    duplicates = {key for key in keys if keys.count(key) > 1}
    assert duplicates == set()


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
