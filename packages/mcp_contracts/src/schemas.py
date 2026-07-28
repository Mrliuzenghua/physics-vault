from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TraceInfoModel(BaseModel):
    source: str
    operator: str
    time: str


class BaseRequestModel(BaseModel):
    version: str = "1.0"
    request_id: str
    task_id: str
    offline_mode: bool = False
    trace: TraceInfoModel | None = None
    payload: dict[str, Any]


class ErrorModel(BaseModel):
    code: str
    message: str
    target: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class WarningModel(BaseModel):
    code: str
    message: str
    target: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BaseResponseModel(BaseModel):
    version: str = "1.0"
    request_id: str
    task_id: str
    success: bool
    warnings: list[WarningModel] = Field(default_factory=list)
    errors: list[ErrorModel] = Field(default_factory=list)
    result: dict[str, Any] | None = None
