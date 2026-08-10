"""Stable input normalization and error payloads for MCP tools."""

from __future__ import annotations

from typing import Any


def clean_args(args: dict[str, Any]) -> dict[str, Any]:
    """Drop only omitted scalar arguments while preserving falsey valid values."""
    return {key: value for key, value in args.items() if value not in (None, "")}


def tool_error(
    code: str,
    message: str,
    *,
    field: str | None = None,
    retryable: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Build the legacy-compatible structured MCP error response."""
    details = {"field": field} if field else {}
    return {
        "ok": False,
        "error": message,
        "error_info": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details,
        },
        **extra,
    }
