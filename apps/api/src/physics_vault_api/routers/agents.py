from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas.agents import (
    AgentConfig,
    AgentConfigResponse,
    AgentConfigUpdateRequest,
    AgentTestResponse,
    QuestionPickerAgentRequest,
    QuestionPickerAgentResponse,
    ReviewLatexCleanupRequest,
    ReviewLatexCleanupResponse,
)
from ..services.claude_code_agent import ClaudeCodeAgentService


def build_agents_router(service: ClaudeCodeAgentService | None = None) -> APIRouter:
    service = service or ClaudeCodeAgentService()
    router = APIRouter(prefix="/api/agents", tags=["agents"])

    @router.get("/config", response_model=AgentConfigResponse)
    def get_config() -> AgentConfigResponse:
        return service.get_config()

    @router.post("/config", response_model=AgentConfigResponse)
    def update_config(payload: AgentConfigUpdateRequest) -> AgentConfigResponse:
        return service.update_config(AgentConfig.model_validate(payload.model_dump()))

    @router.post("/test-claude-code", response_model=AgentTestResponse)
    def test_claude_code() -> AgentTestResponse:
        return service.test_claude_code()

    @router.post("/review-latex-cleanup", response_model=ReviewLatexCleanupResponse)
    def review_latex_cleanup(payload: ReviewLatexCleanupRequest) -> ReviewLatexCleanupResponse:
        result = service.cleanup_review_latex(
            task_id=payload.task_id,
            user_text=payload.user_text,
            dry_run=payload.dry_run,
        )
        if not result.ok:
            raise HTTPException(status_code=404, detail=result.model_dump())
        return result

    @router.post("/question-picker", response_model=QuestionPickerAgentResponse)
    async def question_picker(payload: QuestionPickerAgentRequest) -> QuestionPickerAgentResponse:
        try:
            return await service.pick_questions(payload)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"message": "选题智能体暂时不可用", "detail": str(exc)},
            ) from exc

    @router.post("/question-picker/stream")
    async def question_picker_stream(payload: QuestionPickerAgentRequest) -> StreamingResponse:
        async def event_lines():
            try:
                async for event in service.stream_pick_questions(payload):
                    yield json.dumps(event.model_dump(mode="json", exclude_none=True), ensure_ascii=False) + "\n"
            except Exception as exc:  # noqa: BLE001
                yield json.dumps(
                    {"type": "error", "message": f"选题智能体暂时不可用：{exc}"},
                    ensure_ascii=False,
                ) + "\n"

        return StreamingResponse(
            event_lines(),
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    return router
