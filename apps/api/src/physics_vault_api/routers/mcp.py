from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from ..runtime_config import RuntimeAiConfig, get_runtime_config, update_runtime_config
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


class McpProviderConfigPayload(BaseModel):
    service_type: str = Field(default="OpenAI Compatible", max_length=80)
    base_url: str = Field(default="", max_length=2048)
    api_key: str = Field(default="", max_length=4096)
    model_name: str = Field(default="", max_length=200)
    timeout_seconds: int = Field(default=120, ge=1, le=600)
    max_retries: int = Field(default=3, ge=0, le=10)
    concurrency: int = Field(default=2, ge=1, le=20)


class McpConfigPayload(BaseModel):
    vl: McpProviderConfigPayload
    llm: McpProviderConfigPayload


class McpConfigResponse(BaseModel):
    ok: bool
    mode: str
    vl_configured: bool
    llm_configured: bool


class McpRuntimeConfigResponse(BaseModel):
    vl: dict[str, Any]
    llm: dict[str, Any]
    vl_configured: bool
    llm_configured: bool


class ChatTestMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatTestRequest(BaseModel):
    messages: list[ChatTestMessage] = Field(min_length=1, max_length=100)
    temperature: float = Field(default=0.7, ge=0, le=2)


class ChatTestResponse(BaseModel):
    model: str
    reply: str
    usage: dict[str, Any] | None = None


class RefineQuestionFormatRequest(BaseModel):
    question: dict[str, Any]


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


def _provider_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "code": "AI_PROVIDER_ERROR",
            "message": "AI 服务调用失败，请检查服务地址、模型名称和网络状态。",
            "retryable": True,
            "target": "ai-provider",
            "details": {"error_type": exc.__class__.__name__},
        },
    )


def _config_error(code: str, message: str, target: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": code, "message": message, "retryable": False, "target": target, "details": {}},
    )


def _public_provider_config(config: Any) -> dict[str, Any]:
    return {
        "service_type": config.service_type,
        "base_url": config.base_url,
        "api_key": "",
        "model_name": config.model_name,
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "concurrency": config.concurrency,
    }


def build_mcp_router(service: McpGatewayService) -> APIRouter:
    router = APIRouter(prefix="/api/mcp", tags=["mcp"])

    @router.get("/status", response_model=McpStatusResponse)
    async def get_status() -> McpStatusResponse:
        status = service.status()
        # Surface saved runtime configuration without changing the provider mode.
        cfg = get_runtime_config()
        if status.get("mode") == "http":
            if cfg.vl.api_key:
                status["vl_model"] = cfg.vl.model_name or "(configured)"
            if cfg.llm.api_key:
                status["llm_model"] = cfg.llm.model_name or "(configured)"
        return McpStatusResponse.model_validate(status)

    @router.get("/config", response_model=McpRuntimeConfigResponse)
    async def get_config() -> McpRuntimeConfigResponse:
        """Return saved AI service configuration for the settings page."""
        runtime = get_runtime_config()
        return McpRuntimeConfigResponse(
            vl=_public_provider_config(runtime.vl),
            llm=_public_provider_config(runtime.llm),
            vl_configured=runtime.is_configured("vl"),
            llm_configured=runtime.is_configured("llm"),
        )

    @router.post("/config", response_model=McpConfigResponse)
    async def update_config(payload: McpConfigPayload) -> McpConfigResponse:
        """Receive AI service configuration from the frontend."""
        runtime = RuntimeAiConfig.from_dict(payload.model_dump())
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
            raise _config_error("MISSING_API_KEY", "请先配置文本模型 API Key。", "llm.api_key")
        if not runtime.llm.base_url.strip():
            raise _config_error("MISSING_BASE_URL", "请先配置文本模型服务地址。", "llm.base_url")
        if not runtime.llm.model_name.strip():
            raise _config_error("MISSING_MODEL_NAME", "请先配置文本模型名称。", "llm.model_name")

        messages = [
            {"role": message.role.strip(), "content": message.content}
            for message in request.messages
            if message.content.strip()
        ]
        if not messages:
            raise _config_error("EMPTY_MESSAGES", "至少需要一条非空消息。", "messages")

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
            raise _provider_error(exc) from exc

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

    @router.post("/refine-question-format", response_model=McpTaskResponse)
    async def refine_question_format(request: RefineQuestionFormatRequest) -> McpTaskResponse:
        try:
            data = await service.refine_question_format(request.question)
        except AppError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/parse-document", response_model=McpTaskResponse)
    async def parse_document(request: ParseDocumentRequest) -> McpTaskResponse:
        try:
            data = await service.parse_document(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/detect-question-regions", response_model=McpTaskResponse)
    async def detect_question_regions(request: DetectQuestionRegionsRequest) -> McpTaskResponse:
        try:
            data = await service.detect_question_regions(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/parse-question-region", response_model=McpTaskResponse)
    async def parse_question_region(request: ParseQuestionRegionRequest) -> McpTaskResponse:
        try:
            data = await service.parse_question_region(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
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
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/generate-knowledge", response_model=McpTaskResponse)
    async def generate_knowledge(request: GenerateKnowledgeRequest) -> McpTaskResponse:
        try:
            data = await service.generate_knowledge(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
        return McpTaskResponse(data=data)

    @router.post("/generate-metadata", response_model=McpTaskResponse)
    async def generate_metadata(request: GenerateMetadataRequest) -> McpTaskResponse:
        try:
            data = await service.generate_metadata(request.model_dump())
        except AppError as exc:
            raise _http_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise _provider_error(exc) from exc
        return McpTaskResponse(data=data)

    return router
