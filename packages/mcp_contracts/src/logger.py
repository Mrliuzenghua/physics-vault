"""Structured JSONL logger for MCP calls.

Each call produces one JSON line containing timing, outcome, and (optionally)
summarized request / response data.  Sensitive key patterns are redacted before
writing.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import MCPConfig

# Keys whose values should never appear in logs.
_SENSITIVE_KEY_PATTERNS = ("api_key", "token", "secret", "password", "authorization")


class MCPCallLogger:
    """Writes structured MCP call records to a JSONL file.

    Thread-safe writes are NOT guaranteed — this logger is designed for the
    asyncio event loop where calls are serialised per client instance.
    """

    def __init__(self, config: MCPConfig) -> None:
        self._config = config
        self._log_path: Path | None = None
        if config.log_enabled:
            self._log_path = Path(config.log_dir) / "mcp_calls.jsonl"

    # ── public API ────────────────────────────────────────────────

    def log(
        self,
        *,
        tool_name: str,
        mode: str,
        request_payload: dict[str, Any] | None = None,
        duration_ms: float = 0,
        success: bool = True,
        attempts: int = 1,
        error_code: str | None = None,
        error_message: str | None = None,
        response_result: dict[str, Any] | None = None,
    ) -> None:
        """Write one call record (best-effort; failures are silent)."""
        if not self._config.log_enabled or self._log_path is None:
            return

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "mode": mode,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "attempts": attempts,
        }
        if error_code:
            record["error_code"] = error_code
        if error_message:
            record["error_message"] = error_message

        if self._config.log_requests and request_payload is not None:
            record["request"] = _summarize_dict(request_payload, self._config.log_max_payload_chars)

        if self._config.log_responses and response_result is not None:
            record["response"] = _summarize_dict(response_result, self._config.log_max_payload_chars)

        try:
            self._ensure_dir()
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # logging is best-effort; never crash a real call because of it
            pass

    # ── helpers ───────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)


# ── internal helpers ──────────────────────────────────────────────


def _summarize_dict(data: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Return a redacted + truncated copy suitable for logging."""
    serialized = json.dumps(data, ensure_ascii=False, default=str)
    if len(serialized) <= max_chars:
        return _redact(json.loads(serialized))
    truncated = json.loads(serialized[:max_chars])
    truncated["__truncated__"] = True
    return _redact(truncated)


def _redact(obj: Any) -> Any:
    """Recursively replace sensitive values with '[REDACTED]'."""
    if isinstance(obj, dict):
        return {
            key: "[REDACTED]"
            if any(pattern in key.lower() for pattern in _SENSITIVE_KEY_PATTERNS)
            else _redact(value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    return obj
