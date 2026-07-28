"""MCP runtime configuration sourced from environment variables.

All values have sensible defaults so no .env file is required for local
development with mock mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _bool_env(key: str, default: bool) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def _str_env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass(slots=True)
class MCPConfig:
    """Immutable-ish MCP runtime configuration."""

    # ── Logging ──
    log_enabled: bool = field(default_factory=lambda: _bool_env("PHYSICS_MCP_LOG_ENABLED", True))
    log_dir: str = field(default_factory=lambda: _str_env("PHYSICS_MCP_LOG_DIR", "./data/logs/mcp"))
    log_requests: bool = field(default_factory=lambda: _bool_env("PHYSICS_MCP_LOG_REQUESTS", True))
    log_responses: bool = field(default_factory=lambda: _bool_env("PHYSICS_MCP_LOG_RESPONSES", True))
    log_max_payload_chars: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_LOG_MAX_PAYLOAD_CHARS", 2000))

    # ── Retry ──
    max_retries: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_MAX_RETRIES", 2))
    retry_delay_ms: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_RETRY_DELAY_MS", 500))

    # ── Timeouts ──
    parse_timeout_ms: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_PARSE_TIMEOUT_MS", 60000))
    analysis_timeout_ms: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_ANALYSIS_TIMEOUT_MS", 20000))
    knowledge_timeout_ms: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_KNOWLEDGE_TIMEOUT_MS", 25000))
    metadata_timeout_ms: int = field(default_factory=lambda: _int_env("PHYSICS_MCP_METADATA_TIMEOUT_MS", 40000))
