from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.ai_assistant import AiAssistantChatRequest, AiAssistantChatResponse
from ..services.ai_assistant import AiAssistantService


def build_ai_assistant_router(service: AiAssistantService | None = None) -> APIRouter:
    if service is None:
        service = AiAssistantService()

    router = APIRouter(prefix="/api/ai/assistant", tags=["ai-assistant"])

    @router.post("/chat", response_model=AiAssistantChatResponse, summary="题库上下文 AI 助手")
    async def chat(request: AiAssistantChatRequest) -> AiAssistantChatResponse:
        try:
            return await service.chat(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "题库助手暂时不可用", "detail": str(exc)},
            ) from exc

    return router

