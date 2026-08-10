"""Runtime primitives for question embedding construction.

This module intentionally owns the provider, tokenization and persistence details
used by :mod:`embedding_builds`, keeping that path independent from legacy routes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tiktoken
from fastapi import HTTPException
from openai import OpenAI


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_ALIBABA_MODEL = "text-embedding-v3"
PIPELINE_NAME = "question_embeddings"
PIPELINE_VERSION = "2026-08-08"


def _load_env_file(path: Path, *, embedding_only: bool = False) -> None:
    """Load missing environment variables from the historical API env locations."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if embedding_only and not (
            key == "DASHSCOPE_API_KEY" or key.startswith("PHYSICS_VAULT_")
        ):
            continue
        if key:
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _load_embedding_env() -> None:
    api_source_root = Path(__file__).resolve().parents[2]
    project_root = api_source_root.parents[2]
    api_root = api_source_root.parent
    _load_env_file(api_source_root / ".env")
    _load_env_file(api_root / ".env", embedding_only=True)
    _load_env_file(project_root / ".env")


_load_embedding_env()


def resolve_dashscope_api_key() -> str:
    """Resolve the shared DashScope key without duplicating it into another config file."""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if api_key:
        return api_key

    # The desktop UI persists its Alibaba key in the runtime AI config. Reuse
    # that key for embeddings/rerank when the configured service is DashScope.
    try:
        from ..runtime_config import get_runtime_config

        runtime = get_runtime_config()
        for service in (runtime.vl, runtime.llm):
            base_url = str(service.base_url or "").lower()
            service_type = str(service.service_type or "").lower()
            if service.api_key and ("aliyun" in base_url or "dashscope" in base_url or "alibaba" in service_type):
                return str(service.api_key).strip()
    except Exception:
        pass
    return ""


def dashscope_workspace_id() -> str:
    return os.environ.get("PHYSICS_VAULT_ALIBABA_WORKSPACE_ID", "").strip()


def default_alibaba_embedding_base_url() -> str | None:
    configured = os.environ.get("PHYSICS_VAULT_ALIBABA_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    workspace_id = dashscope_workspace_id()
    if workspace_id:
        return f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    return None


def default_alibaba_rerank_url() -> str | None:
    configured = os.environ.get("PHYSICS_VAULT_RERANK_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    workspace_id = dashscope_workspace_id()
    if workspace_id:
        return (
            f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com"
            "/api/v1/services/rerank/text-rerank/text-rerank"
        )
    return None


def resolve_embedding_client(provider: str, base_url: str | None = None) -> OpenAI:
    normalized = provider.strip().lower()
    if normalized == "alibaba":
        api_key = resolve_dashscope_api_key()
        if not api_key:
            raise HTTPException(status_code=400, detail="DASHSCOPE_API_KEY 未设置")
        return OpenAI(
            api_key=api_key,
            base_url=base_url or default_alibaba_embedding_base_url(),
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY 未设置")
    return OpenAI(api_key=api_key, base_url=base_url)


def resolve_embedding_model(provider: str, model: str) -> str:
    if provider.strip().lower() == "alibaba" and model == DEFAULT_EMBEDDING_MODEL:
        return DEFAULT_ALIBABA_MODEL
    return model


def truncate_text(text: str, _model_name: str, max_tokens: int) -> tuple[str, int]:
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text, len(tokens)
    return encoding.decode(tokens[:max_tokens]), max_tokens


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_question_embedding_text(row: sqlite3.Row) -> str:
    sections: list[str] = []
    if row["canonical_title"]:
        sections.append(f"标题：{row['canonical_title']}")
    structured_topic3 = row["structured_topic3"] if "structured_topic3" in row.keys() else None
    meta_parts = [
        f"模块：{row['module']}" if row["module"] else "",
        f"二级考点：{row['topic2']}" if row["topic2"] else "",
        f"三级知识点：{structured_topic3 or row['topic3']}" if (structured_topic3 or row["topic3"]) else "",
        f"难度：{row['difficulty']}" if row["difficulty"] else "",
        f"题型：{row['question_type']}" if row["question_type"] else "",
    ]
    meta_text = "；".join(part for part in meta_parts if part)
    if meta_text:
        sections.append(meta_text)
    sections.append(f"题干：{(row['stem_text'] or '').strip()}")
    return "\n".join(sections).strip()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_processing_run(connection: sqlite3.Connection, summary: dict[str, Any]) -> str:
    run_id = f"RUN-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    connection.execute(
        """
        INSERT INTO processing_runs (
            run_id, pipeline_name, pipeline_version, status, started_at, operator, summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            PIPELINE_NAME,
            PIPELINE_VERSION,
            "running",
            _utc_now(),
            "fastapi",
            json.dumps(summary, ensure_ascii=False),
        ),
    )
    connection.commit()
    return run_id


def finish_processing_run(
    connection: sqlite3.Connection,
    run_id: str,
    status: str,
    summary: dict[str, Any],
) -> None:
    connection.execute(
        """
        UPDATE processing_runs
        SET status = ?, finished_at = ?, summary_json = ?
        WHERE run_id = ?
        """,
        (status, _utc_now(), json.dumps(summary, ensure_ascii=False), run_id),
    )
    connection.commit()


def upsert_question_embedding(
    connection: sqlite3.Connection,
    *,
    question_id: str,
    vector_type: str,
    model_name: str,
    model_version: str,
    dimensions: int,
    content_hash: str,
    vector: list[float],
) -> None:
    embedding_id = f"EMB-{question_id}-{vector_type}-{model_name}".replace("/", "-")
    connection.execute(
        """
        INSERT INTO embeddings (
            embedding_id, owner_type, owner_id, vector_type, model_name, model_version,
            dimensions, content_hash, vector_json, status, created_at, updated_at
        ) VALUES (?, 'question', ?, ?, ?, ?, ?, ?, ?, 'ready', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(owner_type, owner_id, vector_type, model_name, model_version)
        DO UPDATE SET
            dimensions = excluded.dimensions,
            content_hash = excluded.content_hash,
            vector_json = excluded.vector_json,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            embedding_id,
            question_id,
            vector_type,
            model_name,
            model_version,
            dimensions,
            content_hash,
            json.dumps(vector, ensure_ascii=False),
        ),
    )
