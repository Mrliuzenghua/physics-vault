from __future__ import annotations

import asyncio
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from ..bootstrap import configure_workspace_imports
from ..config import McpSettings

configure_workspace_imports()

from mcp_contracts.src import (  # type: ignore[import-not-found]
    AppError,
    DetectQuestionRegionsInput,
    GenerateAnalysisInput,
    GenerateKnowledgeInput,
    GenerateMetadataInput,
    GenerateQuestionVariantsInput,
    MetadataConstraints,
    MetadataTaskItem,
    ParseDocumentInput,
    ParseQuestionRegionInput,
    QuestionFigure,
    QuestionOption,
    StandardQuestion,
    SubQuestion,
    build_container,
)


class McpGatewayService:
    def __init__(self, settings: McpSettings) -> None:
        self._settings = settings
        self._container = build_container(
            mode=settings.resolved_mode(),
            command_map=settings.command_map,
            cwd=settings.working_directory,
        )
        self._http_client: Any = None  # AiHttpClient, set by notify_config_updated
        self._vl_client: Any = None

    # ── Runtime config update ──────────────────────────────────────

    def notify_config_updated(self, runtime_config: Any) -> None:
        """Called when the frontend pushes new AI config via POST /api/mcp/config."""
        from .ai_http_client import AiHttpClient

        # Use LLM config for text tasks, VL config for vision tasks
        llm = runtime_config.llm
        vl = runtime_config.vl

        self._http_client = None
        self._vl_client = None

        if llm.api_key and llm.base_url:
            self._http_client = AiHttpClient(
                base_url=llm.base_url,
                api_key=llm.api_key,
                model_name=llm.model_name,
                timeout_seconds=llm.timeout_seconds,
                max_retries=llm.max_retries,
            )

        if vl.api_key and vl.base_url:
            if (
                self._http_client is not None
                and vl.base_url == llm.base_url
                and vl.model_name == llm.model_name
                and vl.api_key == llm.api_key
            ):
                self._vl_client = self._http_client
            else:
                self._vl_client = AiHttpClient(
                    base_url=vl.base_url,
                    api_key=vl.api_key,
                    model_name=vl.model_name,
                    timeout_seconds=vl.timeout_seconds,
                    max_retries=vl.max_retries,
                )

    @property
    def _has_http(self) -> bool:
        return self._http_client is not None

    @property
    def _has_vl_http(self) -> bool:
        return self._vl_client is not None

    @property
    def document_parser(self):
        """Expose the MCP DocumentParser contract for use by the import pipeline."""
        return self._container.document_parser

    @property
    def question_variant_generator(self):
        """Expose the MCP QuestionVariantGenerator for use by the variant service."""
        return self._container.question_variant_generator

    def status(self) -> dict[str, Any]:
        mode = self._effective_mode()
        if mode == "http":
            tools = {k: "http-provider" for k in [
                "parse_document", "detect_question_regions",
                "parse_question_region", "generate_analysis",
                "generate_knowledge", "generate_metadata",
            ]}
        elif mode == "mock":
            tools = {
                "parse_document": "mock-provider",
                "detect_question_regions": "mock-provider",
                "parse_question_region": "mock-provider",
                "generate_analysis": "mock-provider",
                "generate_knowledge": "mock-provider",
                "generate_metadata": "mock-provider",
            }
        elif mode == "disabled":
            tools = {
                "parse_document": "disabled",
                "detect_question_regions": "disabled",
                "parse_question_region": "disabled",
                "generate_analysis": "disabled",
                "generate_knowledge": "disabled",
                "generate_metadata": "disabled",
            }
        else:
            tools = self._settings.command_map

        vl_available = self._check_service_available("vl", mode)
        llm_available = self._check_service_available("llm", mode)

        result: dict[str, Any] = {
            "enabled": self._settings.enabled,
            "mode": mode,
            "working_directory": self._settings.working_directory,
            "tools": tools,
            "vl_available": vl_available,
            "llm_available": llm_available,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if self._http_client is not None or self._vl_client is not None:
            result["http_mode"] = True
            if self._http_client is not None:
                result["llm_model"] = self._http_client._model
            if self._vl_client is not None:
                result["vl_model"] = self._vl_client._model
        return result

    def _effective_mode(self) -> str:
        """Return the current effective mode: 'http' > 'mock' > 'disabled' > 'stdio'."""
        if self._http_client is not None or self._vl_client is not None:
            return "http"
        return self._settings.resolved_mode()

    def _check_service_available(self, target: str, mode: str | None = None) -> bool:
        """Lightweight availability check without heavy task execution."""
        if mode is None:
            mode = self._effective_mode()
        if mode == "http":
            return self._vl_client is not None if target == "vl" else self._http_client is not None
        if mode == "mock":
            return True
        if mode == "disabled":
            return False
        # stdio mode — check if the command is configured and exists
        command = self._settings.vl_command if target == "vl" else self._settings.llm_command
        if not command:
            return False
        # shutil.which returns the path if the executable is found, None otherwise
        executable = command.split()[0] if command else ""
        return shutil.which(executable) is not None

    async def test_connection(self, target: str) -> dict[str, Any]:
        mode = self._effective_mode()

        if target not in ("vl", "llm"):
            return {
                "ok": False,
                "target": target,
                "mode": mode,
                "reachable": False,
                "message": f"Invalid target '{target}': must be 'vl' or 'llm'",
            }

        if mode == "http":
            # Quick connectivity check: list models endpoint
            client = self._vl_client if target == "vl" else self._http_client
            if client is None:
                return {"ok": True, "target": target, "mode": mode, "reachable": False,
                        "message": "HTTP client not configured for this target"}
            import urllib.request, json

            def _check_http() -> dict[str, Any]:
                url = f"{client._base_url}/models"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {client._api_key}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
                return {"ok": True, "target": target, "mode": mode, "reachable": True,
                        "message": f"HTTP API reachable: {client._base_url}"}

            try:
                return await asyncio.to_thread(_check_http)
            except Exception as exc:
                return {"ok": True, "target": target, "mode": mode, "reachable": False,
                        "message": f"HTTP API unreachable: {exc}"}

        if mode == "mock":
            return {
                "ok": True,
                "target": target,
                "mode": mode,
                "reachable": True,
                "message": f"Mock {target.upper()} provider is available",
            }

        if mode == "disabled":
            return {
                "ok": True,
                "target": target,
                "mode": mode,
                "reachable": False,
                "message": "AI is disabled (PHYSICS_AI_ENABLED=false or mode=disabled)",
            }

        # stdio mode
        command = self._settings.vl_command if target == "vl" else self._settings.llm_command
        if not command or not command.strip():
            return {
                "ok": True,
                "target": target,
                "mode": mode,
                "reachable": False,
                "message": f"{target.upper()} command is not configured (empty command string)",
            }

        executable = command.strip().split()[0]
        resolved = shutil.which(executable)
        if resolved is None:
            return {
                "ok": True,
                "target": target,
                "mode": mode,
                "reachable": False,
                "message": f"{target.upper()} command '{executable}' not found on system PATH",
            }

        return {
            "ok": True,
            "target": target,
            "mode": mode,
            "reachable": True,
            "message": f"{target.upper()} command is configured: {resolved} (light check only, no heavy task executed)",
        }

    async def parse_document(self, payload: ParseDocumentInput | dict[str, Any]) -> dict[str, Any]:
        if self._has_vl_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            return await asyncio.to_thread(
                self._vl_client.parse_document,
                file_path=d.get("file_path", d.get("source_path", "")),
                file_type=d.get("file_type", "pdf"),
            )
        if isinstance(payload, dict):
            payload = ParseDocumentInput(**payload)
        result = await self._container.document_parser.parse_document(payload)
        return asdict(result)

    async def detect_question_regions(self, payload: DetectQuestionRegionsInput | dict[str, Any]) -> dict[str, Any]:
        if self._has_vl_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            return await asyncio.to_thread(
                self._vl_client.parse_document,
                file_path=d.get("file_path", d.get("image_path", "")),
                file_type=d.get("file_type", "png"),
            )
        if isinstance(payload, dict):
            payload = DetectQuestionRegionsInput(**payload)
        result = await self._container.document_parser.detect_question_regions(payload)
        return asdict(result)

    async def parse_question_region(self, payload: ParseQuestionRegionInput | dict[str, Any]) -> dict[str, Any]:
        if self._has_vl_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            return await asyncio.to_thread(
                self._vl_client.parse_document,
                file_path=d.get("file_path", d.get("image_path", "")),
                file_type=d.get("file_type", "png"),
            )
        if isinstance(payload, dict):
            payload = ParseQuestionRegionInput(**payload)
        result = await self._container.document_parser.parse_question_region(payload)
        return asdict(result)

    async def generate_analysis(self, payload: GenerateAnalysisInput | dict[str, Any]) -> dict[str, Any]:
        if self._has_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            return await asyncio.to_thread(
                self._http_client.generate_analysis,
                question=d.get("question", {}),
                style=d.get("style", "classroom_brief"),
                include_extension=d.get("include_extension", True),
            )
        if isinstance(payload, dict):
            payload = GenerateAnalysisInput(
                question=build_standard_question(payload["question"]),
                style=payload["style"],
                include_extension=payload.get("include_extension", True),
                allow_figure_refs=payload.get("allow_figure_refs", True),
            )
        result = await self._container.analysis_generator.generate_analysis(payload)
        return asdict(result)

    async def generate_knowledge(self, payload: GenerateKnowledgeInput | dict[str, Any]) -> dict[str, Any]:
        if self._has_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            return await asyncio.to_thread(
                self._http_client.generate_knowledge,
                knowledge_points=d.get("knowledge_points", []),
                style=d.get("style", ""),
                length=d.get("length", "medium"),
                include_formula=d.get("include_formula", True),
                include_common_mistakes=d.get("include_common_mistakes", True),
            )
        if isinstance(payload, dict):
            payload = GenerateKnowledgeInput(**payload)
        result = await self._container.knowledge_generator.generate_knowledge(payload)
        return asdict(result)

    async def generate_metadata(self, payload: GenerateMetadataInput | dict[str, Any]) -> dict[str, Any]:
        if self._has_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            items = d.get("items", [])
            questions = [
                {"question_id": item.get("question_id", ""), **(item.get("question", {}))}
                for item in items
            ]
            return await asyncio.to_thread(
                self._http_client.generate_metadata,
                questions=questions,
                fields=d.get("fields", ["knowledge_points", "tags"]),
                only_fill_empty=d.get("only_fill_empty", True),
            )
        if isinstance(payload, dict):
            payload = build_metadata_input(payload)
        result = await self._container.metadata_generator.generate_metadata(payload)
        return asdict(result)

    def clean_import_markdown(self, markdown: str, media_assets: list[dict[str, Any]]) -> dict[str, Any]:
        """Clean Pandoc Markdown with the configured text model when available."""
        if not self._has_http:
            raise RuntimeError("AI HTTP client is not configured")
        return self._http_client.clean_import_markdown(markdown=markdown, media_assets=media_assets)

    def refine_import_questions(self, questions: list[dict[str, Any]]) -> dict[str, Any]:
        """AI-refine locally-split import questions into standard JSON."""
        if not self._has_http:
            raise RuntimeError("AI HTTP client is not configured")
        return self._http_client.refine_import_questions(questions=questions)

    async def generate_question_variants(
        self, payload: GenerateQuestionVariantsInput | dict[str, Any]
    ) -> dict[str, Any]:
        if self._has_http:
            d = payload if isinstance(payload, dict) else asdict(payload)
            return await asyncio.to_thread(
                self._http_client.generate_question_variants,
                source_question=d.get("source_question", {}),
                variant_mode=d.get("variant_mode", "change_numbers"),
                count=d.get("count", 3),
                keep_knowledge_points=d.get("keep_knowledge_points", True),
                target_difficulty=d.get("target_difficulty"),
            )
        if isinstance(payload, dict):
            payload = GenerateQuestionVariantsInput(**payload)
        result = await self._container.question_variant_generator.generate_question_variants(payload)
        return asdict(result)


def build_standard_question(payload: dict[str, Any]) -> StandardQuestion:
    return StandardQuestion(
        question_id=payload["question_id"],
        question_type=payload["question_type"],
        title=payload["title"],
        options=[QuestionOption(**item) for item in payload.get("options", [])],
        answer=payload.get("answer", ""),
        analysis=payload.get("analysis", ""),
        sub_questions=[SubQuestion(**item) for item in payload.get("sub_questions", [])],
        figures=[QuestionFigure(**item) for item in payload.get("figures", [])],
        difficulty=payload.get("difficulty"),
        knowledge_point=payload.get("knowledge_point"),
        tags=list(payload.get("tags", [])),
        source=payload.get("source"),
        import_batch_id=payload.get("import_batch_id"),
    )


def build_metadata_input(payload: dict[str, Any]) -> GenerateMetadataInput:
    return GenerateMetadataInput(
        items=[MetadataTaskItem(**item) for item in payload["items"]],
        fields=payload["fields"],
        constraints=MetadataConstraints(**payload.get("constraints", {})),
        only_fill_empty=payload.get("only_fill_empty", True),
        strict_enum_match=payload.get("strict_enum_match", True),
        prompt_append=payload.get("prompt_append"),
    )


__all__ = ["AppError", "McpGatewayService", "build_metadata_input", "build_standard_question"]
