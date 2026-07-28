from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ErrorCode = Literal[
    "MCP_TIMEOUT",
    "MCP_PROCESS_EXITED",
    "MCP_TOOL_NOT_FOUND",
    "MCP_INVALID_RESPONSE",
    "MCP_CALL_FAILED",
    "SCHEMA_VALIDATION_FAILED",
    "MISSING_REQUIRED_FIELD",
    "ENUM_OUT_OF_RANGE",
    "QUESTION_ID_MISMATCH",
    "KNOWLEDGE_POINT_INVALID",
    "CATALOG_ID_INVALID",
    "IMAGE_REFERENCE_MISSING",
    "QUESTION_NOT_FOUND",
    "DRAFT_NOT_FOUND",
    "IMPORT_BATCH_NOT_FOUND",
    "MANUAL_DATA_PROTECTED",
    "AI_DISABLED",
    "BATCH_PARTIAL_FAILED",
    "COMMIT_VALIDATION_FAILED",
    "ASSET_SAVE_FAILED",
    "DB_WRITE_FAILED",
    "CACHE_WRITE_FAILED",
]

WarningCode = Literal[
    "LOW_CONFIDENCE_OCR",
    "LOW_CONFIDENCE_FORMULA",
    "POSSIBLE_DUPLICATE",
    "MISSING_KNOWLEDGE_POINT",
    "UNUSED_FIGURE",
    "CACHE_MISS",
    "PARTIAL_METADATA_EMPTY",
]


@dataclass(slots=True)
class AppError(Exception):
    code: ErrorCode
    message: str
    target: str | None = None
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(slots=True)
class AppWarning:
    code: WarningCode
    message: str
    target: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def ensure(condition: bool, *, code: ErrorCode, message: str, target: str | None = None) -> None:
    if not condition:
        raise AppError(code=code, message=message, target=target, retryable=False)
