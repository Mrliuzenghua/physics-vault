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


@dataclass(slots=True)
class TaskQueueSettings:
    """Background task settings shared by the API and Dramatiq workers."""

    enabled: bool = False
    broker_url: str = "redis://127.0.0.1:6379/0"
    namespace: str = "physics-vault"
    queue_name: str = "imports"
    control_queue_name: str = "import-control"
    max_retries: int = 4
    min_backoff_ms: int = 5_000
    max_backoff_ms: int = 300_000
    time_limit_ms: int = 1_800_000
    redis_timeout_seconds: int = 2
    worker_heartbeat_interval_seconds: int = 10
    worker_heartbeat_ttl_seconds: int = 35
    stale_task_after_seconds: int = 1_900
    max_active_tasks: int = 8
    max_export_questions: int = 500
    max_export_nodes: int = 2_000

    @property
    def max_attempts(self) -> int:
        return self.max_retries + 1

    @classmethod
    def from_env(cls) -> "TaskQueueSettings":
        broker_url = os.getenv("PHYSICS_TASK_BROKER_URL", "redis://127.0.0.1:6379/0").strip()
        default_enabled = bool(os.getenv("PHYSICS_TASK_BROKER_URL"))
        return cls(
            enabled=_env_flag("PHYSICS_TASK_QUEUE_ENABLED", default_enabled),
            broker_url=broker_url,
            namespace=os.getenv("PHYSICS_TASK_QUEUE_NAMESPACE", "physics-vault").strip() or "physics-vault",
            queue_name=os.getenv("PHYSICS_TASK_QUEUE_NAME", "imports").strip() or "imports",
            control_queue_name=(
                os.getenv("PHYSICS_TASK_CONTROL_QUEUE_NAME", "import-control").strip() or "import-control"
            ),
            max_retries=max(0, _env_int("PHYSICS_TASK_MAX_RETRIES", 4)),
            min_backoff_ms=max(0, _env_int("PHYSICS_TASK_MIN_BACKOFF_MS", 5_000)),
            max_backoff_ms=max(0, _env_int("PHYSICS_TASK_MAX_BACKOFF_MS", 300_000)),
            time_limit_ms=max(1_000, _env_int("PHYSICS_TASK_TIME_LIMIT_MS", 1_800_000)),
            redis_timeout_seconds=max(1, _env_int("PHYSICS_TASK_REDIS_TIMEOUT_SECONDS", 2)),
            worker_heartbeat_interval_seconds=max(
                1, _env_int("PHYSICS_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS", 10)
            ),
            worker_heartbeat_ttl_seconds=max(
                3, _env_int("PHYSICS_TASK_WORKER_HEARTBEAT_TTL_SECONDS", 35)
            ),
            stale_task_after_seconds=max(
                5, _env_int("PHYSICS_TASK_STALE_AFTER_SECONDS", 1_900)
            ),
            max_active_tasks=max(1, _env_int("PHYSICS_TASK_MAX_ACTIVE", 8)),
            max_export_questions=max(1, _env_int("PHYSICS_EXPORT_MAX_QUESTIONS", 500)),
            max_export_nodes=max(1, _env_int("PHYSICS_EXPORT_MAX_NODES", 2_000)),
        )


@dataclass(slots=True)
class LessonExportSettings:
    """Storage limits for immutable lesson export snapshots and artifacts."""

    retention_days: int = 30
    max_snapshot_bytes: int = 25 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "LessonExportSettings":
        return cls(
            retention_days=max(1, _env_int("PHYSICS_EXPORT_RETENTION_DAYS", 30)),
            max_snapshot_bytes=max(
                1024 * 1024,
                _env_int("PHYSICS_EXPORT_MAX_SNAPSHOT_BYTES", 25 * 1024 * 1024),
            ),
        )
