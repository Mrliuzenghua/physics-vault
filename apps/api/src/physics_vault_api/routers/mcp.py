from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

from ..runtime_config import RuntimeAiConfig, update_runtime_config
from ..schemas.mcp_api import (
    DetectQuestionRegionsRequest,
    GenerateAnalysisRequest,
    GenerateKnowledgeRequest,
    GenerateMetadataRequest,
    McpStatusResponse,
    McpTaskResponse,
    ParseDocumentRequest,
    ParseQuestionRegionRequest,
)
from ..schemas.mcp_runtime import McpTestConnectionRequest, McpTestConnectionResponse
from ..services.mcp_gateway import AppError, McpGatewayService


class McpConfigPayload(BaseModel):
    vl: dict[str, Any]
    llm: dict[str, Any]


class McpConfigResponse(BaseModel):
    ok: bool
    mode: str
    vl_configured: bool
    llm_configured: bool


class ChatTestMessage(BaseModel):
    role: str
    content: str


class ChatTestRequest(BaseModel):
    messages: list[ChatTestMessage]
    temperature: float = 0.7


class ChatTestResponse(BaseModel):
    model: str
    reply: str
    usage: dict[str, Any] | None = None


def _http_error(exc: AppError) -> HTTPException:
    status_code = 503 if exc.code in {"AI_DISABLED", "MCP_TIMEOUT", "MCP_PROCESS_EXITED"} else 400
    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "target": exc.target,
            "details": exc.details,
        },
    )


def build_mcp_router(service: McpGatewayService) -> APIRouter:
    router = APIRouter(prefix="/api/mcp", tags=["mcp"])

    @router.get("/status", response_model=McpStatusResponse)
    async def get_status() -> McpStatusResponse:
        status = service.status()
        # Surface saved runtime configuration without changing the provider mode.
        from ..runtime_config import get_runtime_config
        cfg = get_runtime_config()
        if cfg.llm.api_key and status.get("mode") == "http":
            status["llm_model"] = cfg.llm.model_name or "(configured)"
            status["vl_model"] = cfg.vl.model_name or "(configured)"
        return McpStatusResponse.model_validate(status)

    @router.post("/config", response_model=McpConfigResponse)
    async def update_config(payload: McpConfigPayload) -> McpConfigResponse:
        """Receive AI service configuration from the frontend."""
        runtime = RuntimeAiConfig.from_dict({
            "vl": payload.vl,
            "llm": payload.llm,
        })
        update_runtime_config(runtime)
        service.notify_config_updated(runtime)
        return McpConfigResponse(
            ok=True,
            mode="http" if runtime.is_configured() else "mock",
            vl_configured=runtime.is_configured("vl"),
            llm_configured=runtime.is_configured("llm"),
        )

    @router.post("/test-connection", response_model=McpTestConnectionResponse)
    async def test_connection(request: McpTestConnectionRequest) -> McpTestConnectionResponse:
        result = await service.test_connection(request.target)
        if not result["ok"]:
            raise HTTPException(status_code=400, detail=result)
        return McpTestConnectionResponse(**result)

    @router.post("/chat-test", response_model=ChatTestResponse)
    async def chat_test(request: ChatTestRequest) -> ChatTestResponse:
        from ..runtime_config import get_runtime_config

        runtime = get_runtime_config()
        if not runtime.llm.api_key.strip():
            raise HTTPException(status_code=400, detail="Missing API key")
        if not runtime.llm.base_url.strip():
            raise HTTPException(status_code=400, detail="Missing base URL")
        if not runtime.llm.model_name.strip():
            raise HTTPException(status_code=400, detail="Missing model name")

        messages = [
            {"role": message.role.strip(), "content": message.content}
            for message in request.messages
            if message.content.strip()
        ]
        if not messages:
            raise HTTPException(status_code=400, detail="At least one message is required")

        try:
            client = OpenAI(
                api_key=runtime.llm.api_key,
                base_url=runtime.llm.base_url,
                timeout=runtime.llm.timeout_seconds,
            )
            response = client.chat.completions.create(
                model=runtime.llm.model_name,
                messages=messages,
                temperature=request.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"AI request failed: {exc}") from exc

        reply = ""
        if response.choices:
            content = response.choices[0].message.content
            if isinstance(content, str):
                reply = content
            elif isinstance(content, list):
                reply = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )

        return ChatTestResponse(
            model=response.model or runtime.llm.model_name,
            reply=reply,
            usage=response.usage.model_dump() if response.usage else None,
        )

    @router.post("/parse-document", response_model=McpTaskResponse)
    async def parse_document(request: ParseDocumentRequest) -> McpTaskResponse:
        try:
            data = await service.parse_document(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/detect-question-regions", response_model=McpTaskResponse)
    async def detect_question_regions(request: DetectQuestionRegionsRequest) -> McpTaskResponse:
        try:
            data = await service.detect_question_regions(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/parse-question-region", response_model=McpTaskResponse)
    async def parse_question_region(request: ParseQuestionRegionRequest) -> McpTaskResponse:
        try:
            data = await service.parse_question_region(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/generate-analysis", response_model=McpTaskResponse)
    async def generate_analysis(request: GenerateAnalysisRequest) -> McpTaskResponse:
        try:
            data = await service.generate_analysis(
                {
                    "question": request.question.model_dump(),
                    "style": request.style,
                    "include_extension": request.include_extension,
                    "allow_figure_refs": request.allow_figure_refs,
                }
            )
        except AppError as exc:
            raise _http_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/generate-knowledge", response_model=McpTaskResponse)
    async def generate_knowledge(request: GenerateKnowledgeRequest) -> McpTaskResponse:
        try:
            data = await service.generate_knowledge(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/generate-metadata", response_model=McpTaskResponse)
    async def generate_metadata(request: GenerateMetadataRequest) -> McpTaskResponse:
        try:
            data = await service.generate_metadata(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        return McpTaskResponse(data=data)

    return router
