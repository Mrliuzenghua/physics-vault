"""Compatibility-preserving named response envelopes for legacy map payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, RootModel


class HealthResponse(BaseModel):
    """Minimal readiness result for browser clients and platform probes."""

    status: str


class IntegerMapResponse(RootModel[dict[str, int]]):
    """A named API contract for string-keyed integer maps."""


class StringMapResponse(RootModel[dict[str, str]]):
    """A named API contract for string-keyed string maps."""


class BooleanMapResponse(RootModel[dict[str, bool]]):
    """A named API contract for string-keyed boolean maps."""


class ObjectMapResponse(RootModel[dict[str, Any]]):
    """A named compatibility contract for documented opaque object maps."""


class ObjectListResponse(RootModel[list[dict[str, Any]]]):
    """A named compatibility contract for documented opaque object lists."""
