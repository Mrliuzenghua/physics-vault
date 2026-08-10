"""Small, dependency-free correlation context for requests and durable jobs."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from uuid import uuid4


TRACE_ID_HEADER = "X-Trace-ID"
TASK_ID_HEADER = "X-Task-ID"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

_trace_id: ContextVar[str | None] = ContextVar("physics_vault_trace_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("physics_vault_task_id", default=None)


def normalize_identifier(value: str | None) -> str | None:
    """Accept portable correlation IDs while refusing unbounded header values."""
    candidate = str(value or "").strip()
    return candidate if _IDENTIFIER_RE.fullmatch(candidate) else None


def new_trace_id() -> str:
    return str(uuid4())


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_task_id() -> str | None:
    return _task_id.get()


def resolve_trace_id(value: str | None = None) -> str:
    return normalize_identifier(value) or current_trace_id() or new_trace_id()


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    trace_id: str
    task_id: str | None = None

    def as_request_context(self) -> dict[str, str]:
        values = {"trace_id": self.trace_id, "task_id": self.task_id}
        return {key: value for key, value in values.items() if value}


def current_context() -> CorrelationContext:
    return CorrelationContext(trace_id=resolve_trace_id(), task_id=current_task_id())


@contextmanager
def correlation_context(
    *,
    trace_id: str | None = None,
    task_id: str | None = None,
) -> Iterator[CorrelationContext]:
    context = CorrelationContext(
        trace_id=resolve_trace_id(trace_id),
        task_id=normalize_identifier(task_id) or current_task_id(),
    )
    trace_token = _trace_id.set(context.trace_id)
    task_token = _task_id.set(context.task_id)
    try:
        yield context
    finally:
        _task_id.reset(task_token)
        _trace_id.reset(trace_token)
