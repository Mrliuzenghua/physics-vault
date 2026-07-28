from __future__ import annotations

import os
from dataclasses import dataclass

from .client import McpClient, StdioMcpClient
from .config import MCPConfig
from .contracts import (
    AnalysisGenerator,
    DocumentParser,
    KnowledgeGenerator,
    MetadataGenerator,
    QuestionVariantGenerator,
)
from .providers import (
    DisabledAnalysisGenerator,
    DisabledDocumentParser,
    DisabledKnowledgeGenerator,
    DisabledMetadataGenerator,
    DisabledQuestionVariantGenerator,
    McpAnalysisGenerator,
    McpDocumentParser,
    McpKnowledgeGenerator,
    McpMetadataGenerator,
    McpQuestionVariantGenerator,
    MockAnalysisGenerator,
    MockDocumentParser,
    MockKnowledgeGenerator,
    MockMetadataGenerator,
    MockQuestionVariantGenerator,
)


@dataclass(slots=True)
class ServiceContainer:
    document_parser: DocumentParser
    analysis_generator: AnalysisGenerator
    knowledge_generator: KnowledgeGenerator
    metadata_generator: MetadataGenerator
    question_variant_generator: QuestionVariantGenerator


def build_container(
    mode: str = "mock",
    client: McpClient | None = None,
    command_map: dict[str, str] | None = None,
    cwd: str | None = None,
    config: MCPConfig | None = None,
) -> ServiceContainer:
    """Assemble an MCP service container from configuration.

    The *config* parameter carries log/retry/timeout settings.  When omitted
    a default ``MCPConfig`` is constructed from environment variables (see
    ``PHYSICS_MCP_*``).
    """
    normalized = mode.strip().lower()
    mcp_config = config or MCPConfig()

    if normalized == "disabled":
        return ServiceContainer(
            document_parser=DisabledDocumentParser(),
            analysis_generator=DisabledAnalysisGenerator(),
            knowledge_generator=DisabledKnowledgeGenerator(),
            metadata_generator=DisabledMetadataGenerator(),
            question_variant_generator=DisabledQuestionVariantGenerator(),
        )

    if normalized == "stdio":
        resolved_command_map = command_map or {
            "parse_document": os.environ.get("PHYSICS_MCP_VL_COMMAND", ""),
            "detect_question_regions": os.environ.get("PHYSICS_MCP_VL_COMMAND", ""),
            "parse_question_region": os.environ.get("PHYSICS_MCP_VL_COMMAND", ""),
            "generate_analysis": os.environ.get("PHYSICS_MCP_LLM_COMMAND", ""),
            "generate_knowledge": os.environ.get("PHYSICS_MCP_LLM_COMMAND", ""),
            "generate_metadata": os.environ.get("PHYSICS_MCP_LLM_COMMAND", ""),
            "generate_question_variants": os.environ.get("PHYSICS_MCP_LLM_COMMAND", ""),
        }
        mcp_client = client or StdioMcpClient(
            command_map=resolved_command_map,
            cwd=cwd,
            config=mcp_config,
        )
        return ServiceContainer(
            document_parser=McpDocumentParser(
                mcp_client, timeout_ms=mcp_config.parse_timeout_ms
            ),
            analysis_generator=McpAnalysisGenerator(
                mcp_client, timeout_ms=mcp_config.analysis_timeout_ms
            ),
            knowledge_generator=McpKnowledgeGenerator(
                mcp_client, timeout_ms=mcp_config.knowledge_timeout_ms
            ),
            metadata_generator=McpMetadataGenerator(
                mcp_client, timeout_ms=mcp_config.metadata_timeout_ms
            ),
            question_variant_generator=McpQuestionVariantGenerator(
                mcp_client, timeout_ms=mcp_config.metadata_timeout_ms
            ),
        )

    # mock (default)
    return ServiceContainer(
        document_parser=MockDocumentParser(),
        analysis_generator=MockAnalysisGenerator(),
        knowledge_generator=MockKnowledgeGenerator(),
        metadata_generator=MockMetadataGenerator(),
        question_variant_generator=MockQuestionVariantGenerator(),
    )
