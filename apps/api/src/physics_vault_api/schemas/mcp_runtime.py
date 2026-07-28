from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class McpTestConnectionRequest(BaseModel):
    target: Literal["vl", "llm"] = Field(
        description="Which service to test: 'vl' for vision-language, 'llm' for text generation",
    )


class McpTestConnectionResponse(BaseModel):
    ok: bool = Field(description="Whether the request was processed (distinct from reachable)")
    target: str
    mode: str
    reachable: bool = Field(description="Whether the target service is reachable")
    message: str = Field(description="Human-readable status message")
