from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


@dataclass(slots=True)
class McpSettings:
    mode: str = "mock"
    working_directory: str | None = None
    vl_command: str = ""
    llm_command: str = ""
    enabled: bool = True
    parse_timeout_ms: int = 60000
    analysis_timeout_ms: int = 20000
    knowledge_timeout_ms: int = 25000
    metadata_timeout_ms: int = 40000

    @property
    def command_map(self) -> dict[str, str]:
        return {
            "parse_document": self.vl_command,
            "detect_question_regions": self.vl_command,
            "parse_question_region": self.vl_command,
            "generate_analysis": self.llm_command,
            "generate_knowledge": self.llm_command,
            "generate_metadata": self.llm_command,
        }

    @classmethod
    def from_env(cls) -> "McpSettings":
        project_root = Path(__file__).resolve().parents[4]
        return cls(
            mode=os.getenv("PHYSICS_MCP_MODE", "mock").strip().lower(),
            working_directory=os.getenv("PHYSICS_MCP_WORKDIR") or str(project_root),
            vl_command=os.getenv("PHYSICS_MCP_VL_COMMAND", "").strip(),
            llm_command=os.getenv("PHYSICS_MCP_LLM_COMMAND", "").strip(),
            enabled=_env_flag("PHYSICS_AI_ENABLED", True),
            parse_timeout_ms=_env_int("PHYSICS_MCP_PARSE_TIMEOUT_MS", 60000),
            analysis_timeout_ms=_env_int("PHYSICS_MCP_ANALYSIS_TIMEOUT_MS", 20000),
            knowledge_timeout_ms=_env_int("PHYSICS_MCP_KNOWLEDGE_TIMEOUT_MS", 25000),
            metadata_timeout_ms=_env_int("PHYSICS_MCP_METADATA_TIMEOUT_MS", 40000),
        )

    def resolved_mode(self) -> str:
        if not self.enabled:
            return "disabled"
        return self.mode
