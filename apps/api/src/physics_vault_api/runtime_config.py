"""
Runtime-updatable AI configuration store.

Unlike McpSettings (frozen at startup from env vars), this module
accepts configuration pushed from the frontend at runtime via the
POST /api/mcp/config endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any


DEFAULT_VL_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_VL_MODEL = "qwen-vl-max"
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-pro"


@dataclass
class AiServiceConfig:
    """Configuration for one AI service (VL or LLM)."""
    service_type: str = "OpenAI Compatible"
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    timeout_seconds: int = 120
    max_retries: int = 3
    concurrency: int = 2


@dataclass
class RuntimeAiConfig:
    """Full runtime AI configuration matching the frontend McpConfig shape."""
    vl: AiServiceConfig = field(default_factory=AiServiceConfig)
    llm: AiServiceConfig = field(default_factory=AiServiceConfig)

    def is_configured(self, target: str = "llm") -> bool:
        """Check whether a given service has a real API key set."""
        svc = self.vl if target == "vl" else self.llm
        return bool(svc.api_key and svc.base_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vl": self.vl.__dict__,
            "llm": self.llm.__dict__,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeAiConfig":
        def _parse_svc(raw: dict[str, Any], *, defaults: AiServiceConfig) -> AiServiceConfig:
            service_type = str(raw.get("service_type") or defaults.service_type)
            base_url = str(raw.get("base_url") or defaults.base_url)
            model_name = str(raw.get("model_name") or defaults.model_name)
            lower_service = service_type.lower()
            lower_base = base_url.lower()
            lower_model = model_name.lower()

            if defaults.service_type == "Alibaba DashScope":
                if "openai.com" in lower_base or lower_model.startswith("gpt-"):
                    base_url = defaults.base_url
                    model_name = defaults.model_name
                if "qwen" in lower_service:
                    service_type = defaults.service_type

            if defaults.service_type == "DeepSeek":
                if "openai.com" in lower_base or lower_model.startswith("gpt-"):
                    base_url = defaults.base_url
                    model_name = defaults.model_name
                if lower_service in {"deepseek", "deepseek ai"}:
                    service_type = defaults.service_type

            return AiServiceConfig(
                service_type=service_type,
                base_url=base_url,
                api_key=str(raw.get("api_key") or defaults.api_key),
                model_name=model_name,
                timeout_seconds=int(raw.get("timeout_seconds") or defaults.timeout_seconds),
                max_retries=int(raw.get("max_retries") or defaults.max_retries),
                concurrency=int(raw.get("concurrency") or defaults.concurrency),
            )
        return cls(
            vl=_parse_svc(data.get("vl", {}), defaults=default_vl_config()),
            llm=_parse_svc(data.get("llm", {}), defaults=default_llm_config()),
        )


import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Persist config to a file so it survives backend restarts
_CONFIG_FILE = Path(os.getenv("PHYSICS_RUNTIME_CONFIG_PATH",
    Path(__file__).resolve().parents[3] / "data" / "runtime_ai_config.json"))


def _load_from_file() -> RuntimeAiConfig | None:
    try:
        if _CONFIG_FILE.exists():
            data = json.loads(_CONFIG_FILE.read_text("utf-8"))
            cfg = RuntimeAiConfig.from_dict(data)
            if cfg.is_configured():
                logger.info("Loaded runtime AI config from %s (model=%s)", _CONFIG_FILE, cfg.llm.model_name)
                return cfg
    except Exception:
        pass
    return None


def default_vl_config() -> AiServiceConfig:
    return AiServiceConfig(
        service_type="Alibaba DashScope",
        base_url=os.getenv("PHYSICS_VL_BASE_URL", DEFAULT_VL_BASE_URL),
        api_key=os.getenv("PHYSICS_VL_API_KEY") or os.getenv("DASHSCOPE_API_KEY", ""),
        model_name=os.getenv("PHYSICS_VL_MODEL", DEFAULT_VL_MODEL),
        timeout_seconds=int(os.getenv("PHYSICS_VL_TIMEOUT_SECONDS", "120")),
        max_retries=int(os.getenv("PHYSICS_VL_MAX_RETRIES", "2")),
        concurrency=int(os.getenv("PHYSICS_VL_CONCURRENCY", "1")),
    )


def default_llm_config() -> AiServiceConfig:
    return AiServiceConfig(
        service_type="DeepSeek",
        base_url=os.getenv("PHYSICS_LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        api_key=os.getenv("PHYSICS_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
        model_name=os.getenv("PHYSICS_LLM_MODEL", DEFAULT_LLM_MODEL),
        timeout_seconds=int(os.getenv("PHYSICS_LLM_TIMEOUT_SECONDS", "120")),
        max_retries=int(os.getenv("PHYSICS_LLM_MAX_RETRIES", "2")),
        concurrency=int(os.getenv("PHYSICS_LLM_CONCURRENCY", "2")),
    )


def default_runtime_config() -> RuntimeAiConfig:
    return RuntimeAiConfig(vl=default_vl_config(), llm=default_llm_config())


def _save_to_file(config: RuntimeAiConfig) -> None:
    try:
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        logger.warning("Failed to persist runtime AI config to %s", _CONFIG_FILE)


# Singleton — try to restore from file, fall back to empty
_runtime_config: RuntimeAiConfig = _load_from_file() or default_runtime_config()


def get_runtime_config() -> RuntimeAiConfig:
    """Return the current runtime AI configuration."""
    return _runtime_config


def update_runtime_config(config: RuntimeAiConfig) -> None:
    """Replace the runtime AI configuration and persist to disk."""
    global _runtime_config
    _runtime_config = config
    _save_to_file(config)
