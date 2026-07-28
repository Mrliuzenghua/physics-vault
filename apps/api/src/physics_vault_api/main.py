"""
Unified runtime entrypoint for the Physics Vault API.

The modular app is the primary runtime. Legacy routes are merged only when
their path/method signature is not already provided by the modular routers.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import BaseRoute

from .app import create_app as create_modular_app
from .legacy_app import app as legacy_app


def _route_key(route: BaseRoute) -> tuple[str | None, frozenset[str]]:
    methods = getattr(route, "methods", None)
    return getattr(route, "path", None), frozenset(methods or ())


def _covered_route_keys(routes: Iterable[BaseRoute]) -> set[tuple[str | None, frozenset[str]]]:
    return {_route_key(route) for route in routes}


def create_app() -> FastAPI:
    """Build the unified application."""
    app = create_modular_app()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    modular_route_keys = _covered_route_keys(app.routes)
    merged = 0
    for route in legacy_app.routes:
        if _route_key(route) not in modular_route_keys:
            app.router.routes.append(route)
            merged += 1

    print(f"[main] merged {merged} legacy routes into modular app")
    return app


app = create_app()

__all__ = ["app", "create_app"]
