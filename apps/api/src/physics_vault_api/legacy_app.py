from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tiktoken
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from .database import connect_db
from .paths import default_db_path


API_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = API_ROOT.parents[2]
DB_PATH = default_db_path()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


for env_path in (
    API_ROOT / ".env",
    VAULT_ROOT / ".env",
):
    load_env_file(env_path)


DEFAULT_EMBEDDING_PROVIDER = os.environ.get("PHYSICS_VAULT_EMBEDDING_PROVIDER", "openai").strip().lower()
DEFAULT_EMBEDDING_MODEL = os.environ.get("PHYSICS_VAULT_EMBEDDING_MODEL", "text-embedding-3-small").strip()
DEFAULT_EMBEDDING_VECTOR_TYPE = os.environ.get("PHYSICS_VAULT_EMBEDDING_VECTOR_TYPE", "semantic_search").strip()
DEFAULT_ALIBABA_BASE_URL = os.environ.get("PHYSICS_VAULT_ALIBABA_BASE_URL")
DEFAULT_ALIBABA_MODEL = "text-embedding-v4"
DEFAULT_MAX_EMBEDDING_TOKENS = 8000
PIPELINE_NAME = "question_embeddings"
PIPELINE_VERSION = "2026-07-21"


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")
    return connect_db(DB_PATH)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def fetch_distinct_strings(connection: sqlite3.Connection, sql: str) -> list[str]:
    return [row[0] for row in connection.execute(sql).fetchall() if row[0] not in (None, "")]


def fetch_knowledge_points_for_questions(
    connection: sqlite3.Connection,
    question_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not question_ids:
        return {}
    placeholders = ",".join("?" for _ in question_ids)
    rows = connection.execute(
        f"""
        SELECT
            question_id,
            rank,
            topic1_id,
            topic1_name,
            topic2_id,
            topic2_name,
            topic3_id,
            topic3_name,
            source_chapter,
            source,
            confidence,
            note
        FROM question_knowledge_points_view
        WHERE question_id IN ({placeholders})
        ORDER BY question_id, rank
        """,
        question_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        payload = row_to_dict(row)
        question_id = payload.pop("question_id")
        grouped.setdefault(question_id, []).append(payload)
    return grouped


def question_payload(row: sqlite3.Row, knowledge_map: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    payload = {key: value for key, value in row_to_dict(row).items() if key != "stem_text"}
    if payload.get("difficulty") is not None:
        payload["difficulty"] = str(payload["difficulty"])
    payload["image_filenames"] = parse_json_list(payload.pop("image_filenames_json", None))
    payload["image_asset_ids"] = parse_json_list(payload.pop("image_asset_ids_json", None))
    payload["knowledge_points"] = knowledge_map.get(row["question_id"], [])
    return payload


def resolve_embedding_client(provider: str, base_url: str | None = None) -> OpenAI:
    normalized = provider.strip().lower()
    if normalized == "alibaba":
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=400, detail="DASHSCOPE_API_KEY 未设置")
        return OpenAI(api_key=api_key, base_url=base_url or DEFAULT_ALIBABA_BASE_URL)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY 未设置")
    return OpenAI(api_key=api_key, base_url=base_url)


def resolve_embedding_model(provider: str, model: str) -> str:
    normalized = provider.strip().lower()
    if normalized == "alibaba" and model == DEFAULT_EMBEDDING_MODEL:
        return DEFAULT_ALIBABA_MODEL
    return model


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_encoding(model_name: str):
    if model_name.startswith("text-embedding-3"):
        return tiktoken.get_encoding("cl100k_base")
    return tiktoken.get_encoding("cl100k_base")


def truncate_text(text: str, model_name: str, max_tokens: int) -> tuple[str, int]:
    encoding = get_encoding(model_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text, len(tokens)
    trimmed = encoding.decode(tokens[:max_tokens])
    return trimmed, max_tokens


def compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_question_embedding_text(row: sqlite3.Row) -> str:
    sections: list[str] = []
    if row["canonical_title"]:
        sections.append(f"标题：{row['canonical_title']}")

    meta_parts = [
        f"试卷：{row['paper_id']}" if row["paper_id"] else "",
        f"模块：{row['module']}" if row["module"] else "",
        f"二级考点：{row['topic2']}" if row["topic2"] else "",
        f"三级考点：{row['topic3']}" if row["topic3"] else "",
        f"难度：{row['difficulty']}" if row["difficulty"] else "",
        f"题型：{row['question_type']}" if row["question_type"] else "",
    ]
    meta_text = "；".join(part for part in meta_parts if part)
    if meta_text:
        sections.append(meta_text)

    sections.append(f"题干：{(row['stem_text'] or '').strip()}")
    return "\n".join(sections).strip()


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
            utc_now(),
            "fastapi",
            json.dumps(summary, ensure_ascii=False),
        ),
    )
    connection.commit()
    return run_id


def finish_processing_run(connection: sqlite3.Connection, run_id: str, status: str, summary: dict[str, Any]) -> None:
    connection.execute(
        """
        UPDATE processing_runs
        SET status = ?, finished_at = ?, summary_json = ?
        WHERE run_id = ?
        """,
        (status, utc_now(), json.dumps(summary, ensure_ascii=False), run_id),
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


def parse_vector_json(raw: str | None) -> list[float]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    floats: list[float] = []
    for item in value:
        try:
            floats.append(float(item))
        except (TypeError, ValueError):
            return []
    return floats


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def fetch_question_candidates(
    connection: sqlite3.Connection,
    *,
    paper_id: str | None = None,
    year: int | None = None,
    region: str | None = None,
    exam_type: str | None = None,
    topic2: str | None = None,
    topic3: str | None = None,
    module: str | None = None,
    topic1_id: str | None = None,
    topic2_id: str | None = None,
    topic3_id: str | None = None,
    topic_rank: int | None = None,
    difficulty: str | None = None,
    question_type: str | None = None,
    status: str | None = None,
    has_media: bool | None = None,
    image_count_min: int = 0,
    q: str | None = None,
    apply_keyword_filter: bool = True,
    limit: int | None = None,
    offset: int = 0,
) -> list[sqlite3.Row]:
    sql = """
        SELECT DISTINCT
            q.question_id,
            q.canonical_title,
            q.module,
            q.topic2,
            q.topic3,
            q.difficulty,
            q.question_type AS type,
            q.status,
            q.has_media,
            q.primary_paper_id,
            q.primary_question_no,
            q.vault_markdown_path,
            qti.stem_text,
            qti.image_filenames_json,
            qti.image_asset_ids_json,
            COALESCE(qti.image_count, 0) AS image_count
        FROM questions q
        LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
        LEFT JOIN papers p ON p.paper_id = q.primary_paper_id
    """
    where: list[str] = ["COALESCE(qti.image_count, 0) >= ?"]
    params: list[Any] = [image_count_min]

    def add_exact(value: Any, expression: str) -> None:
        if value is not None:
            where.append(f"{expression} = ?")
            params.append(value)

    def add_knowledge_exists(condition: str, values: list[Any]) -> None:
        rank_clause = ""
        rank_params: list[Any] = []
        if topic_rank is not None:
            rank_clause = " AND kpv.rank = ?"
            rank_params.append(topic_rank)
        where.append(
            f"""
            EXISTS (
                SELECT 1
                FROM question_knowledge_points_view kpv
                WHERE kpv.question_id = q.question_id
                  {rank_clause}
                  AND {condition}
            )
            """
        )
        params.extend(rank_params)
        params.extend(values)

    add_exact(paper_id, "q.primary_paper_id")
    add_exact(year, "p.year")
    add_exact(region, "p.region")
    add_exact(exam_type, "p.exam_type")
    if module is not None:
        where.append(
            """
            (
                q.module = ?
                OR EXISTS (
                    SELECT 1
                    FROM question_knowledge_points_view kpv
                    WHERE kpv.question_id = q.question_id
                      AND (? IS NULL OR kpv.rank = ?)
                      AND kpv.topic1_name = ?
                )
            )
            """
        )
        params.extend([module, topic_rank, topic_rank, module])
    if topic2 is not None:
        where.append(
            """
            (
                q.topic2 = ?
                OR EXISTS (
                    SELECT 1
                    FROM question_knowledge_points_view kpv
                    WHERE kpv.question_id = q.question_id
                      AND (? IS NULL OR kpv.rank = ?)
                      AND kpv.topic2_name = ?
                )
            )
            """
        )
        params.extend([topic2, topic_rank, topic_rank, topic2])
    if topic3 is not None:
        where.append(
            """
            (
                q.topic3 = ?
                OR EXISTS (
                    SELECT 1
                    FROM question_knowledge_points_view kpv
                    WHERE kpv.question_id = q.question_id
                      AND (? IS NULL OR kpv.rank = ?)
                      AND kpv.topic3_name = ?
                )
            )
            """
        )
        params.extend([topic3, topic_rank, topic_rank, topic3])
    if topic1_id is not None:
        add_knowledge_exists("kpv.topic1_id = ?", [topic1_id])
    if topic2_id is not None:
        add_knowledge_exists("kpv.topic2_id = ?", [topic2_id])
    if topic3_id is not None:
        add_knowledge_exists("kpv.topic3_id = ?", [topic3_id])
    add_exact(difficulty, "q.difficulty")
    add_exact(question_type, "q.question_type")
    add_exact(status, "q.status")
    if has_media is not None:
        where.append("q.has_media = ?")
        params.append(int(has_media))
    if apply_keyword_filter:
        where.append(
            """
            (
              ? IS NULL
              OR q.canonical_title LIKE '%' || ? || '%'
              OR qti.stem_text LIKE '%' || ? || '%'
            )
            """
        )
        params.extend([q, q, q])
    sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY q.primary_question_no, q.question_id"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    return connection.execute(sql, params).fetchall()


def compute_keyword_match(query: str | None, row: sqlite3.Row) -> bool:
    if not query:
        return False
    normalized = query.strip().lower()
    if not normalized:
        return False
    title = (row["canonical_title"] or "").lower()
    stem = (row["stem_text"] or "").lower()
    return normalized in title or normalized in stem


def semantic_similarity_for_row(
    row: sqlite3.Row,
    *,
    embedding_map: dict[str, list[float]],
    query_vector: list[float] | None,
) -> float | None:
    if query_vector is None:
        return None
    vector = embedding_map.get(row["question_id"])
    if not vector:
        return None
    return cosine_similarity(query_vector, vector)


def topic_consistency_bonus(
    row: sqlite3.Row,
    *,
    module: str | None,
    topic2: str | None,
    topic3: str | None,
    difficulty: str | None,
    question_type: str | None,
) -> float:
    bonus = 0.0
    if module and row["module"] == module:
        bonus += 0.08
    if topic2 and row["topic2"] == topic2:
        bonus += 0.12
    if topic3 and row["topic3"] == topic3:
        bonus += 0.18
    if difficulty and row["difficulty"] == difficulty:
        bonus += 0.03
    if question_type and row["type"] == question_type:
        bonus += 0.03
    return bonus


class HealthResponse(BaseModel):
    status: str
    database_path: str


class PaperSummary(BaseModel):
    paper_id: str
    year: int | None = None
    exam_type: str
    region: str | None = None
    paper_name: str
    subject: str
    status: str
    question_count: int = 0


class PaperDetail(PaperSummary):
    source_path: str | None = None
    source_format: str | None = None
    notes: str | None = None
    created_at: str
    updated_at: str


class KnowledgePointLink(BaseModel):
    rank: int
    topic1_id: str
    topic1_name: str
    topic2_id: str
    topic2_name: str
    topic3_id: str
    topic3_name: str
    source_chapter: str | None = None
    source: str | None = None
    confidence: float | None = None
    note: str | None = None


class KnowledgePointItem(BaseModel):
    topic3_id: str
    topic3_name: str
    topic2_id: str
    topic2_name: str
    topic1_id: str
    topic1_name: str
    source_chapter: str | None = None
    status: str
    note: str | None = None


class QuestionKnowledgePointUpsert(BaseModel):
    topic3_id: str
    source: str = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    note: str | None = None


class QuestionKnowledgePointBatchItem(QuestionKnowledgePointUpsert):
    rank: int = Field(ge=1, le=3)


class QuestionSummary(BaseModel):
    question_id: str
    canonical_title: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    difficulty: str | None = None
    question_type: str | None = Field(default=None, alias="type")
    status: str
    has_media: bool
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    source: str | None = None
    knowledge_points: list[KnowledgePointLink] = Field(default_factory=list)


class UnifiedQuestionSearchItem(QuestionSummary):
    image_filenames: list[str] = Field(default_factory=list)
    image_asset_ids: list[str] = Field(default_factory=list)
    image_count: int = 0
    similarity: float | None = None
    keyword_match: bool = False
    search_mode: str
    score: float | None = None


class QuestionDetail(QuestionSummary):
    content_hash: str | None = None
    schema_version: str
    title_text: str | None = None
    stem_text: str | None = None
    stem_clean_text: str | None = None
    source_id: str | None = None
    image_asset_ids: list[str] = Field(default_factory=list)
    image_filenames: list[str] = Field(default_factory=list)
    image_count: int = 0
    answer_text: str | None = None
    analysis_text: str | None = None
    tips_text: str | None = None
    options_json: str | None = None
    created_at: str
    updated_at: str


class QuestionAsset(BaseModel):
    link_id: str
    asset_id: str
    role: str
    sort_order: int
    placeholder_key: str | None = None
    is_primary: bool
    is_verified: bool
    filename: str
    file_path: str
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    description: str | None = None
    binding_confidence: float | None = None
    verified: bool


class ImageAssetItem(BaseModel):
    asset_id: str
    filename: str
    file_path: str
    paper_id: str | None = None
    question_id: str | None = None
    source_id: str | None = None
    role: str
    sort_order: int
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    description: str | None = None
    extracted_text: str | None = None
    image_type: str | None = None
    binding_confidence: float | None = None
    verified: bool


class ReviewQueueItem(BaseModel):
    review_id: str
    entity_type: str
    entity_id: str
    queue_type: str
    status: str
    priority: int
    reason: str | None = None
    payload_json: str | None = None
    created_at: str
    updated_at: str


class ProcessingRunItem(BaseModel):
    run_id: str
    pipeline_name: str
    pipeline_version: str
    paper_id: str | None = None
    question_id: str | None = None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    operator: str | None = None
    summary_json: str | None = None


class EmbeddingStatusItem(BaseModel):
    model_name: str
    model_version: str | None = None
    vector_type: str
    owner_count: int
    last_updated_at: str | None = None


class EmbeddingBuildRequest(BaseModel):
    provider: str = DEFAULT_EMBEDDING_PROVIDER
    model: str = DEFAULT_EMBEDDING_MODEL
    vector_type: str = DEFAULT_EMBEDDING_VECTOR_TYPE
    model_version: str = ""
    base_url: str | None = None
    dimensions: int | None = None
    limit: int | None = Field(default=None, ge=1, le=5000)
    question_ids: list[str] = Field(default_factory=list)
    since_question_id: str | None = None
    max_tokens: int = Field(default=DEFAULT_MAX_EMBEDDING_TOKENS, ge=128, le=8192)
    batch_size: int = Field(default=20, ge=1, le=100)
    force: bool = False
    dry_run: bool = False


class EmbeddingBuildResponse(BaseModel):
    run_id: str
    provider: str
    model_name: str
    vector_type: str
    processed_count: int
    embedded_count: int
    skipped_count: int
    failed_count: int
    dry_run: bool


class SemanticSearchQuestionItem(BaseModel):
    question_id: str
    canonical_title: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    difficulty: str | None = None
    question_type: str | None = Field(default=None, alias="type")
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    similarity: float


class FilterFacets(BaseModel):
    years: list[int] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    exam_types: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    topic1_ids: list[str] = Field(default_factory=list)
    topic1_values: list[str] = Field(default_factory=list)
    topic2_ids: list[str] = Field(default_factory=list)
    topic2_values: list[str] = Field(default_factory=list)
    topic3_ids: list[str] = Field(default_factory=list)
    topic3_values: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    question_types: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


app = FastAPI(
    title="Physics Vault API",
    description="Compatibility endpoints backed by the configured canonical database.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/files/{file_path:path}")
def serve_file(file_path: str):
    """Serve static files (images, etc.) from the vault root."""
    full_path = VAULT_ROOT / file_path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    response = FileResponse(str(full_path))
    response.headers.setdefault("Cache-Control", "public, max-age=86400")
    return response


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Physics Vault Browser</title>
  <style>
    :root {
      --bg: #f5efe3;
      --panel: #fffaf1;
      --line: #d6c7a8;
      --ink: #2f271a;
      --muted: #72644d;
      --accent: #8d6a29;
      --accent-soft: #efe1b9;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fff7df 0, transparent 24%),
        linear-gradient(180deg, #faf4e8 0%, var(--bg) 100%);
    }
    .wrap {
      width: min(1200px, calc(100vw - 28px));
      margin: 20px auto 40px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 10px 28px rgba(77, 58, 20, 0.08);
    }
    .hero {
      padding: 26px;
      margin-bottom: 16px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 34px;
    }
    .hero p {
      margin: 0;
      line-height: 1.7;
      color: var(--muted);
    }
    .layout {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 16px;
    }
    .panel {
      padding: 18px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 18px;
    }
    .field {
      margin-bottom: 12px;
    }
    .field label {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 14px;
    }
    input, select {
      width: 100%;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #fffdf8;
      color: var(--ink);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .tab, button {
      border: 0;
      border-radius: 10px;
      padding: 9px 14px;
      cursor: pointer;
      font-weight: 600;
    }
    .tab {
      background: #fffdf8;
      border: 1px solid var(--line);
      color: var(--ink);
    }
    .tab.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    .actions {
      display: flex;
      gap: 10px;
      margin-top: 12px;
    }
    .primary {
      background: var(--accent);
      color: white;
    }
    .secondary {
      background: var(--accent-soft);
      color: #4d3d16;
    }
    .status {
      min-height: 22px;
      margin-bottom: 12px;
      color: var(--muted);
    }
    .list {
      display: grid;
      gap: 12px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      background: #fffef9;
    }
    .card h3 {
      margin: 0 0 8px;
      font-size: 18px;
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }
    .chip {
      font-size: 12px;
      padding: 4px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #5a4718;
    }
    .path, .snippet {
      font-size: 13px;
      line-height: 1.6;
      color: var(--muted);
      word-break: break-all;
    }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Physics Vault Browser</h1>
      <p>按年份、地区、模块、考点、题型、图片关联直接浏览数据库，也可以切到图片模式查看题图绑定结果。</p>
    </section>
    <div class="layout">
      <aside class="panel">
        <h2>筛选</h2>
        <div class="field">
          <label for="keyword">关键词</label>
          <input id="keyword" placeholder="搜题干、标题、图片说明">
        </div>
        <div class="row">
          <div class="field">
            <label for="year">年份</label>
            <select id="year"><option value="">全部</option></select>
          </div>
          <div class="field">
            <label for="region">地区</label>
            <select id="region"><option value="">全部</option></select>
          </div>
        </div>
        <div class="row">
          <div class="field">
            <label for="examType">考试类型</label>
            <select id="examType"><option value="">全部</option></select>
          </div>
          <div class="field">
            <label for="hasMedia">图片关联</label>
            <select id="hasMedia">
              <option value="">全部</option>
              <option value="true">只看带图</option>
              <option value="false">只看无图</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label for="module">模块</label>
          <select id="module"><option value="">全部</option></select>
        </div>
        <div class="row">
          <div class="field">
            <label for="topic2">二级考点</label>
            <select id="topic2"><option value="">全部</option></select>
          </div>
          <div class="field">
            <label for="topic3">三级考点</label>
            <select id="topic3"><option value="">全部</option></select>
          </div>
        </div>
        <div class="row">
          <div class="field">
            <label for="difficulty">难度</label>
            <select id="difficulty"><option value="">全部</option></select>
          </div>
          <div class="field">
            <label for="questionType">题型</label>
            <select id="questionType"><option value="">全部</option></select>
          </div>
        </div>
        <div class="row">
          <div class="field">
            <label for="statusFilter">状态</label>
            <select id="statusFilter"><option value="">全部</option></select>
          </div>
          <div class="field">
            <label for="imageCountMin">最少图片数</label>
            <input id="imageCountMin" type="number" min="0" value="0">
          </div>
        </div>
        <div class="actions">
          <button class="primary" id="searchButton">查询</button>
          <button class="secondary" id="resetButton">重置</button>
        </div>
      </aside>
      <main class="panel">
        <div class="tabs">
          <button class="tab active" data-mode="questions">题目</button>
          <button class="tab" data-mode="images">图片</button>
          <button class="tab" data-mode="papers">试卷</button>
        </div>
        <div class="status" id="status">准备就绪</div>
        <div class="list" id="results"></div>
      </main>
    </div>
  </div>
  <script>
    const els = {
      keyword: document.getElementById("keyword"),
      year: document.getElementById("year"),
      region: document.getElementById("region"),
      examType: document.getElementById("examType"),
      hasMedia: document.getElementById("hasMedia"),
      module: document.getElementById("module"),
      topic2: document.getElementById("topic2"),
      topic3: document.getElementById("topic3"),
      difficulty: document.getElementById("difficulty"),
      questionType: document.getElementById("questionType"),
      statusFilter: document.getElementById("statusFilter"),
      imageCountMin: document.getElementById("imageCountMin"),
      status: document.getElementById("status"),
      results: document.getElementById("results"),
      tabs: [...document.querySelectorAll(".tab")],
      searchButton: document.getElementById("searchButton"),
      resetButton: document.getElementById("resetButton"),
    };

    let mode = "questions";

    function setStatus(text) {
      els.status.textContent = text;
    }

    function fillSelect(select, values) {
      const current = select.value;
      select.innerHTML = '<option value="">全部</option>';
      values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
      select.value = current;
    }

    async function loadFacets() {
      const response = await fetch("/filters/facets");
      const data = await response.json();
      fillSelect(els.year, data.years);
      fillSelect(els.region, data.regions);
      fillSelect(els.examType, data.exam_types);
      fillSelect(els.module, data.modules);
      fillSelect(els.topic2, data.topic2_values);
      fillSelect(els.topic3, data.topic3_values);
      fillSelect(els.difficulty, data.difficulties);
      fillSelect(els.questionType, data.question_types);
      fillSelect(els.statusFilter, data.statuses);
    }

    function buildCommonParams() {
      const params = new URLSearchParams();
      if (els.keyword.value.trim()) params.set("q", els.keyword.value.trim());
      if (els.year.value) params.set("year", els.year.value);
      if (els.region.value) params.set("region", els.region.value);
      if (els.examType.value) params.set("exam_type", els.examType.value);
      if (els.hasMedia.value) params.set("has_media", els.hasMedia.value);
      if (els.module.value) params.set("module", els.module.value);
      if (els.topic2.value) params.set("topic2", els.topic2.value);
      if (els.topic3.value) params.set("topic3", els.topic3.value);
      if (els.difficulty.value) params.set("difficulty", els.difficulty.value);
      if (els.questionType.value) params.set("question_type", els.questionType.value);
      if (els.statusFilter.value) params.set("status", els.statusFilter.value);
      if (Number(els.imageCountMin.value) > 0) params.set("image_count_min", els.imageCountMin.value);
      params.set("limit", "50");
      return params;
    }

    function renderCards(items, render) {
      els.results.innerHTML = "";
      if (!items.length) {
        els.results.innerHTML = '<div class="card"><div class="snippet">没有查到结果。</div></div>';
        return;
      }
      items.forEach((item) => {
        const card = document.createElement("article");
        card.className = "card";
        card.innerHTML = render(item);
        els.results.appendChild(card);
      });
    }

    async function searchQuestions() {
      const params = buildCommonParams();
      if (params.has("q")) {
        params.set("query", params.get("q"));
        params.delete("q");
      }
      params.set("search_mode", params.has("query") ? "strict" : "browse");
      const response = await fetch(`/search/questions?${params.toString()}`);
      const data = await response.json();
      setStatus(`题目结果 ${data.length} 条`);
      renderCards(data, (item) => `
        <h3>${item.canonical_title || item.question_id}</h3>
        <div class="meta">
          <span class="chip">${item.primary_paper_id || "无试卷"}</span>
          ${item.primary_question_no ? `<span class="chip">第 ${item.primary_question_no} 题</span>` : ""}
          ${item.module ? `<span class="chip">${item.module}</span>` : ""}
          ${item.topic3 ? `<span class="chip">${item.topic3}</span>` : ""}
          ${item.type ? `<span class="chip">${item.type}</span>` : ""}
          <span class="chip">${item.has_media ? "带图" : "无图"}</span>
        </div>
        <div class="path">${item.vault_markdown_path || ""}</div>
      `);
    }

    async function searchImages() {
      const params = buildCommonParams();
      const response = await fetch(`/images?${params.toString()}`);
      const data = await response.json();
      setStatus(`图片结果 ${data.length} 条`);
      renderCards(data, (item) => `
        <h3>${item.filename}</h3>
        <div class="meta">
          ${item.paper_id ? `<span class="chip">${item.paper_id}</span>` : ""}
          ${item.question_id ? `<span class="chip">${item.question_id}</span>` : ""}
          <span class="chip">${item.role}</span>
          ${item.image_type ? `<span class="chip">${item.image_type}</span>` : ""}
          <span class="chip">${item.verified ? "已验证" : "未验证"}</span>
        </div>
        <div class="path">${item.file_path}</div>
        <div class="snippet">${item.description || item.extracted_text || ""}</div>
      `);
    }

    async function searchPapers() {
      const params = new URLSearchParams();
      if (els.keyword.value.trim()) params.set("q", els.keyword.value.trim());
      if (els.year.value) params.set("year", els.year.value);
      if (els.region.value) params.set("region", els.region.value);
      if (els.examType.value) params.set("exam_type", els.examType.value);
      params.set("limit", "50");
      const response = await fetch(`/papers?${params.toString()}`);
      const data = await response.json();
      setStatus(`试卷结果 ${data.length} 条`);
      renderCards(data, (item) => `
        <h3>${item.paper_name}</h3>
        <div class="meta">
          <span class="chip">${item.paper_id}</span>
          ${item.year ? `<span class="chip">${item.year}</span>` : ""}
          ${item.region ? `<span class="chip">${item.region}</span>` : ""}
          <span class="chip">${item.question_count} 题</span>
          <span class="chip">${item.status}</span>
        </div>
      `);
    }

    async function search() {
      setStatus("查询中...");
      if (mode === "questions") return searchQuestions();
      if (mode === "images") return searchImages();
      return searchPapers();
    }

    function resetFilters() {
      [
        els.keyword, els.year, els.region, els.examType, els.hasMedia,
        els.module, els.topic2, els.topic3, els.difficulty,
        els.questionType, els.statusFilter
      ].forEach((el) => { el.value = ""; });
      els.imageCountMin.value = "0";
      search();
    }

    els.tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        mode = tab.dataset.mode;
        els.tabs.forEach((item) => item.classList.toggle("active", item === tab));
        search();
      });
    });
    els.searchButton.addEventListener("click", search);
    els.resetButton.addEventListener("click", resetFilters);

    loadFacets().then(search).catch((error) => {
      setStatus(`加载失败：${error}`);
    });
  </script>
</body>
</html>
"""


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    with closing(get_connection()) as connection:
        connection.execute("SELECT 1")
    return HealthResponse(status="ok", database_path=str(DB_PATH))


@app.get("/papers", response_model=list[PaperSummary])
def list_papers(
    year: int | None = None,
    region: str | None = None,
    exam_type: str | None = None,
    q: str | None = Query(default=None, description="Search in paper name or paper id"),
    subject: str = "PHY",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[PaperSummary]:
    sql = """
        SELECT
            p.paper_id,
            p.year,
            p.exam_type,
            p.region,
            p.paper_name,
            p.subject,
            p.status,
            COUNT(qn.question_id) AS question_count
        FROM papers p
        LEFT JOIN questions qn ON qn.primary_paper_id = p.paper_id
        WHERE (? IS NULL OR p.year = ?)
          AND (? IS NULL OR p.region = ?)
          AND (? IS NULL OR p.exam_type = ?)
          AND (? IS NULL OR p.subject = ?)
          AND (
              ? IS NULL
              OR p.paper_name LIKE '%' || ? || '%'
              OR p.paper_id LIKE '%' || ? || '%'
          )
        GROUP BY p.paper_id
        ORDER BY p.year DESC, p.paper_id
        LIMIT ? OFFSET ?
    """
    params = [year, year, region, region, exam_type, exam_type, subject, subject, q, q, q, limit, offset]
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [PaperSummary(**row_to_dict(row)) for row in rows]


@app.get("/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str) -> PaperDetail:
    sql = """
        SELECT
            p.paper_id,
            p.year,
            p.exam_type,
            p.region,
            p.paper_name,
            p.subject,
            p.status,
            p.source_path,
            p.source_format,
            p.notes,
            p.created_at,
            p.updated_at,
            COUNT(q.question_id) AS question_count
        FROM papers p
        LEFT JOIN questions q ON q.primary_paper_id = p.paper_id
        WHERE p.paper_id = ?
        GROUP BY p.paper_id
    """
    with closing(get_connection()) as connection:
        row = connection.execute(sql, (paper_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperDetail(**row_to_dict(row))


@app.get("/papers/{paper_id}/questions", response_model=list[QuestionSummary])
def list_paper_questions(paper_id: str) -> list[QuestionSummary]:
    sql = """
        SELECT
            question_id,
            canonical_title,
            module,
            topic2,
            topic3,
            difficulty,
            question_type AS type,
            status,
            has_media,
            primary_paper_id,
            primary_question_no,
            vault_markdown_path
        FROM questions
        WHERE primary_paper_id = ?
        ORDER BY primary_question_no, question_id
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, (paper_id,)).fetchall()
        knowledge_map = fetch_knowledge_points_for_questions(
            connection,
            [row["question_id"] for row in rows],
        )
    return [QuestionSummary(**question_payload(row, knowledge_map)) for row in rows]


@app.get(
    "/search/questions",
    response_model=list[UnifiedQuestionSearchItem],
    summary="统一题目检索",
    description=(
        "统一题目检索入口。"
        "browse 用于纯筛选浏览；"
        "strict 用于按关键词和考点精确找题；"
        "hybrid 用于在筛选候选集内做向量相似排序；"
        "similar 用于长题干相似题和查重。"
    ),
)
def unified_search_questions(
    query: str | None = Query(
        default=None,
        description="查询词或长题干。browse 模式可留空；strict、hybrid、similar 模式必填。",
    ),
    search_mode: str = Query(
        default="strict",
        pattern="^(browse|strict|hybrid|similar)$",
        description=(
            "检索模式。browse=纯浏览；strict=关键词+考点精确检索；"
            "hybrid=候选集内混合排序；similar=全库相似题/查重。"
        ),
    ),
    paper_id: str | None = None,
    year: int | None = None,
    region: str | None = None,
    exam_type: str | None = None,
    topic2: str | None = None,
    topic3: str | None = None,
    module: str | None = None,
    topic1_id: str | None = Query(default=None, description="Filter by first-level topic id, for example T1-ELC"),
    topic2_id: str | None = Query(default=None, description="Filter by second-level topic id, for example T2-ELC-001"),
    topic3_id: str | None = Query(default=None, description="Filter by third-level topic id, for example T3-ELC-031"),
    topic_rank: int | None = Query(default=None, ge=1, le=3, description="Limit topic filters to rank 1, 2, or 3"),
    difficulty: str | None = None,
    question_type: str | None = None,
    status: str | None = None,
    has_media: bool | None = None,
    image_count_min: int = 0,
    provider: str = DEFAULT_EMBEDDING_PROVIDER,
    model: str = DEFAULT_EMBEDDING_MODEL,
    vector_type: str = DEFAULT_EMBEDDING_VECTOR_TYPE,
    model_version: str = "",
    base_url: str | None = None,
    candidate_limit: int = Query(
        default=500,
        description="hybrid 和 similar 模式下的候选集上限。值越大召回越宽，但速度越慢。",
    ),
    limit: int = Query(default=20, description="返回结果数量上限。"),
    offset: int = Query(default=0, description="结果偏移量，用于分页。"),
) -> list[UnifiedQuestionSearchItem]:
    if search_mode in {"strict", "hybrid", "similar"} and not query:
        raise HTTPException(status_code=400, detail="query is required for strict, hybrid, or similar search")
    if candidate_limit < 1 or candidate_limit > 5000:
        raise HTTPException(status_code=400, detail="candidate_limit must be between 1 and 5000")

    query_vector: list[float] | None = None
    embedding_map: dict[str, list[float]] = {}
    resolved_model = resolve_embedding_model(provider, model)

    if search_mode in {"hybrid", "similar"}:
        client = resolve_embedding_client(provider, base_url)
        response = client.embeddings.create(
            model=resolved_model,
            input=query,
            encoding_format="float",
        )
        query_vector = response.data[0].embedding

    with closing(get_connection()) as connection:
        if search_mode == "browse":
            candidate_rows = fetch_question_candidates(
                connection,
                paper_id=paper_id,
                year=year,
                region=region,
                exam_type=exam_type,
                topic2=topic2,
                topic3=topic3,
                module=module,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                topic_rank=topic_rank,
                difficulty=difficulty,
                question_type=question_type,
                status=status,
                has_media=has_media,
                image_count_min=image_count_min,
                q=None,
                apply_keyword_filter=False,
                limit=limit,
                offset=offset,
            )
        elif search_mode == "strict":
            candidate_rows = fetch_question_candidates(
                connection,
                paper_id=paper_id,
                year=year,
                region=region,
                exam_type=exam_type,
                topic2=topic2,
                topic3=topic3,
                module=module,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                topic_rank=topic_rank,
                difficulty=difficulty,
                question_type=question_type,
                status=status,
                has_media=has_media,
                image_count_min=image_count_min,
                q=query,
                apply_keyword_filter=True,
                limit=limit,
                offset=offset,
            )
        elif search_mode == "hybrid":
            candidate_rows = fetch_question_candidates(
                connection,
                paper_id=paper_id,
                year=year,
                region=region,
                exam_type=exam_type,
                topic2=topic2,
                topic3=topic3,
                module=module,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                topic_rank=topic_rank,
                difficulty=difficulty,
                question_type=question_type,
                status=status,
                has_media=has_media,
                image_count_min=image_count_min,
                q=None,
                apply_keyword_filter=False,
                limit=candidate_limit,
                offset=0,
            )
        else:
            candidate_rows = fetch_question_candidates(
                connection,
                paper_id=paper_id,
                year=year,
                region=region,
                exam_type=exam_type,
                topic2=None,
                topic3=None,
                module=None,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                topic_rank=topic_rank,
                difficulty=difficulty,
                question_type=question_type,
                status=status,
                has_media=has_media,
                image_count_min=image_count_min,
                q=None,
                apply_keyword_filter=False,
                limit=candidate_limit,
                offset=0,
            )

        if search_mode in {"hybrid", "similar"}:
            embedding_rows = connection.execute(
                """
                SELECT owner_id, vector_json
                FROM embeddings
                WHERE owner_type = 'question'
                  AND vector_type = ?
                  AND model_name = ?
                  AND COALESCE(model_version, '') = COALESCE(?, '')
                """,
                (vector_type, resolved_model, model_version),
            ).fetchall()
            embedding_map = {row["owner_id"]: parse_vector_json(row["vector_json"]) for row in embedding_rows}
        knowledge_map = fetch_knowledge_points_for_questions(
            connection,
            [row["question_id"] for row in candidate_rows],
        )

    if search_mode == "browse":
        return [
            UnifiedQuestionSearchItem(
                **question_payload(row, knowledge_map),
                similarity=None,
                keyword_match=False,
                search_mode="browse",
                score=None,
            )
            for row in candidate_rows
        ]

    if search_mode == "strict":
        return [
            UnifiedQuestionSearchItem(
                **question_payload(row, knowledge_map),
                similarity=None,
                keyword_match=compute_keyword_match(query, row),
                search_mode="strict",
                score=1.0 if compute_keyword_match(query, row) else 0.0,
            )
            for row in candidate_rows
        ]

    scored: list[UnifiedQuestionSearchItem] = []
    for row in candidate_rows:
        similarity = semantic_similarity_for_row(
            row,
            embedding_map=embedding_map,
            query_vector=query_vector,
        )
        if similarity is None:
            continue
        keyword_match = compute_keyword_match(query, row)
        bonus = topic_consistency_bonus(
            row,
            module=module,
            topic2=topic2,
            topic3=topic3,
            difficulty=difficulty,
            question_type=question_type,
        )
        if search_mode == "hybrid":
            score = similarity * 0.7 + (0.12 if keyword_match else 0.0) + bonus
        else:
            score = similarity + (0.02 if keyword_match else 0.0)
        scored.append(
            UnifiedQuestionSearchItem(
                **question_payload(row, knowledge_map),
                similarity=similarity,
                keyword_match=keyword_match,
                search_mode=search_mode,
                score=score,
            )
        )

    scored.sort(key=lambda item: (item.score or 0.0, item.similarity or 0.0), reverse=True)
    return scored[offset:offset + limit]


@app.get("/questions/{question_id}", response_model=QuestionDetail)
def get_question(question_id: str) -> QuestionDetail:
    sql = """
        SELECT
            q.question_id,
            q.canonical_title,
            q.module,
            q.topic2,
            q.topic3,
            q.difficulty,
            q.question_type AS type,
            q.status,
            q.has_media,
            q.primary_paper_id,
            q.primary_question_no,
            q.vault_markdown_path,
            q.content_hash,
            q.schema_version,
            q.created_at,
            q.updated_at,
            qti.stem_text,
            qti.title_text,
            qti.stem_clean_text,
            qti.source_id,
            COALESCE(qti.source_text, q.source, q.primary_paper_id) AS source,
            qti.image_asset_ids_json,
            qti.image_filenames_json,
            COALESCE(qti.image_count, 0) AS image_count,
            qti.answer_text,
            qti.analysis_text,
            qti.tips_text,
            qti.options_json
        FROM questions q
        LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
        WHERE q.question_id = ?
    """
    with closing(get_connection()) as connection:
        row = connection.execute(sql, (question_id,)).fetchone()
        knowledge_map = fetch_knowledge_points_for_questions(connection, [question_id])
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    payload = row_to_dict(row)
    if payload.get("difficulty") is not None:
        payload["difficulty"] = str(payload["difficulty"])
    payload["image_asset_ids"] = parse_json_list(payload.pop("image_asset_ids_json", None))
    payload["image_filenames"] = parse_json_list(payload.pop("image_filenames_json", None))
    payload["knowledge_points"] = knowledge_map.get(question_id, [])
    return QuestionDetail(**payload)


@app.put("/questions/{question_id}", response_model=dict)
def update_question(question_id: str, payload: dict) -> dict:
    """更新单道题的全部字段。

    将请求体中的字段合并到 question_id 对应的记录中，通过
    ``QuestionWriteService.save_batch`` 写入数据库。
    修改前会自动生成一条历史版本快照。

    图片关联数据由独立的图片管理 API 维护，不通过此接口修改。
    如果请求体中不包含 ``figures``，则保留数据库中已有的图片数据。
    """
    payload["question_id"] = question_id
    from .services.question_write import QuestionWriteService

    # Preserve existing image data if the payload doesn't include it.
    # The frontend strips image fields from PUT payloads because images
    # are managed by the separate /api/questions/{id}/images API.
    if not payload.get("figures"):
        with closing(get_connection()) as conn:
            tx_row = conn.execute(
                """
                SELECT image_asset_ids_json, image_filenames_json, image_count
                FROM question_text_index WHERE question_id = ?
                """,
                (question_id,),
            ).fetchone()
        if tx_row:
            asset_ids = parse_json_list(tx_row["image_asset_ids_json"])
            filenames = parse_json_list(tx_row["image_filenames_json"])
            payload["figures"] = [
                {"fig_uuid": aid, "local_path": fn}
                for aid, fn in zip(asset_ids, filenames)
            ]

    service = QuestionWriteService()
    result = service.save_batch([payload])

    if result.saved_count == 0:
        raise HTTPException(
            status_code=500,
            detail={"message": "保存失败", "errors": result.errors},
        )

    # Return the full question data so the frontend can update its state
    # without an extra GET round-trip.
    sql = """
        SELECT
            q.question_id, q.canonical_title, q.module, q.topic2, q.topic3,
            q.difficulty, q.question_type AS type, q.status, q.has_media,
            q.primary_paper_id, q.primary_question_no, q.vault_markdown_path,
            q.content_hash, q.schema_version, q.created_at, q.updated_at,
            qti.stem_text, qti.title_text, qti.stem_clean_text, qti.source_id,
            COALESCE(qti.source_text, q.source, q.primary_paper_id) AS source,
            qti.image_asset_ids_json, qti.image_filenames_json,
            COALESCE(qti.image_count, 0) AS image_count,
            qti.answer_text, qti.analysis_text, qti.tips_text, qti.options_json
        FROM questions q
        LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
        WHERE q.question_id = ?
    """
    with closing(get_connection()) as conn:
        row = conn.execute(sql, (question_id,)).fetchone()
        knowledge_map = fetch_knowledge_points_for_questions(conn, [question_id])
    if row is None:
        raise HTTPException(status_code=404, detail="保存后查询失败")
    data = row_to_dict(row)
    if data.get("difficulty") is not None:
        data["difficulty"] = str(data["difficulty"])
    data["image_asset_ids"] = parse_json_list(data.pop("image_asset_ids_json", None))
    data["image_filenames"] = parse_json_list(data.pop("image_filenames_json", None))
    data["knowledge_points"] = knowledge_map.get(question_id, [])
    return data


@app.get("/questions/{question_id}/knowledge-points", response_model=list[KnowledgePointLink])
def get_question_knowledge_points(question_id: str) -> list[KnowledgePointLink]:
    with closing(get_connection()) as connection:
        exists = connection.execute(
            "SELECT 1 FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Question not found")
        knowledge_map = fetch_knowledge_points_for_questions(connection, [question_id])
    return [KnowledgePointLink(**item) for item in knowledge_map.get(question_id, [])]


@app.put("/questions/{question_id}/knowledge-points", response_model=list[KnowledgePointLink])
def replace_question_knowledge_points(
    question_id: str,
    payload: list[QuestionKnowledgePointBatchItem],
) -> list[KnowledgePointLink]:
    if not payload:
        raise HTTPException(status_code=400, detail="At least one knowledge point is required")
    if len(payload) > 3:
        raise HTTPException(status_code=400, detail="A question can have at most 3 knowledge points")

    ranks = [item.rank for item in payload]
    if len(set(ranks)) != len(ranks):
        raise HTTPException(status_code=400, detail="Duplicate ranks are not allowed")
    if 1 not in ranks:
        raise HTTPException(status_code=400, detail="rank=1 is required as the primary topic")

    topic3_ids = [item.topic3_id for item in payload]
    if len(set(topic3_ids)) != len(topic3_ids):
        raise HTTPException(status_code=400, detail="Duplicate topic3_id values are not allowed")

    with closing(get_connection()) as connection:
        exists = connection.execute(
            "SELECT 1 FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Question not found")

        placeholders = ",".join("?" for _ in topic3_ids)
        existing_topic_ids = {
            row["topic3_id"]
            for row in connection.execute(
                f"SELECT topic3_id FROM knowledge_points WHERE topic3_id IN ({placeholders}) AND status = 'active'",
                topic3_ids,
            ).fetchall()
        }
        missing_topic_ids = sorted(set(topic3_ids) - existing_topic_ids)
        if missing_topic_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Knowledge point not found: {', '.join(missing_topic_ids)}",
            )

        try:
            connection.execute(
                "DELETE FROM question_knowledge_points WHERE question_id = ? AND rank BETWEEN 1 AND 3",
                (question_id,),
            )
            connection.executemany(
                """
                INSERT INTO question_knowledge_points (
                    question_id, rank, topic3_id, source, confidence, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                [
                    (
                        question_id,
                        item.rank,
                        item.topic3_id,
                        item.source,
                        item.confidence,
                        item.note,
                    )
                    for item in payload
                ],
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise HTTPException(status_code=400, detail="Knowledge point replacement failed") from exc

        knowledge_map = fetch_knowledge_points_for_questions(connection, [question_id])
    return [KnowledgePointLink(**item) for item in knowledge_map.get(question_id, [])]


@app.put("/questions/{question_id}/knowledge-points/{rank}", response_model=KnowledgePointLink)
def upsert_question_knowledge_point(
    question_id: str,
    rank: int,
    payload: QuestionKnowledgePointUpsert,
) -> KnowledgePointLink:
    if rank < 1 or rank > 3:
        raise HTTPException(status_code=400, detail="rank must be 1, 2, or 3")
    with closing(get_connection()) as connection:
        exists = connection.execute(
            "SELECT 1 FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Question not found")
        topic_exists = connection.execute(
            "SELECT 1 FROM knowledge_points WHERE topic3_id = ? AND status = 'active'",
            (payload.topic3_id,),
        ).fetchone()
        if topic_exists is None:
            raise HTTPException(status_code=404, detail="Knowledge point not found")
        try:
            connection.execute(
                """
                INSERT INTO question_knowledge_points (
                    question_id, rank, topic3_id, source, confidence, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id, rank) DO UPDATE SET
                    topic3_id = excluded.topic3_id,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    note = excluded.note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    question_id,
                    rank,
                    payload.topic3_id,
                    payload.source,
                    payload.confidence,
                    payload.note,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=400,
                detail="This question already uses the same topic3_id at another rank",
            ) from exc
        row = connection.execute(
            """
            SELECT
                rank,
                topic1_id,
                topic1_name,
                topic2_id,
                topic2_name,
                topic3_id,
                topic3_name,
                source_chapter,
                source,
                confidence,
                note
            FROM question_knowledge_points_view
            WHERE question_id = ? AND rank = ?
            """,
            (question_id, rank),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Knowledge point update failed")
    return KnowledgePointLink(**row_to_dict(row))


@app.delete("/questions/{question_id}/knowledge-points/{rank}", response_model=dict[str, str])
def delete_question_knowledge_point(question_id: str, rank: int) -> dict[str, str]:
    if rank < 1 or rank > 3:
        raise HTTPException(status_code=400, detail="rank must be 1, 2, or 3")
    if rank == 1:
        raise HTTPException(status_code=400, detail="rank=1 is the primary topic and should not be deleted")
    with closing(get_connection()) as connection:
        connection.execute(
            "DELETE FROM question_knowledge_points WHERE question_id = ? AND rank = ?",
            (question_id, rank),
        )
        connection.commit()
    return {"status": "deleted"}


@app.get("/questions/{question_id}/assets", response_model=list[QuestionAsset])
def get_question_assets(question_id: str) -> list[QuestionAsset]:
    sql = """
        SELECT
            qa.link_id,
            qa.asset_id,
            qa.role,
            qa.sort_order,
            qa.placeholder_key,
            qa.is_primary,
            qa.is_verified,
            ia.filename,
            ia.file_path,
            ia.mime_type,
            ia.width,
            ia.height,
            ia.description,
            ia.binding_confidence,
            ia.verified
        FROM question_assets qa
        INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
        WHERE qa.question_id = ?
        ORDER BY qa.sort_order, qa.asset_id
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, (question_id,)).fetchall()
    return [QuestionAsset(**row_to_dict(row)) for row in rows]


@app.get("/images", response_model=list[ImageAssetItem])
def list_images(
    q: str | None = Query(default=None, description="Search in filename, description, extracted_text"),
    paper_id: str | None = None,
    question_id: str | None = None,
    year: int | None = None,
    region: str | None = None,
    exam_type: str | None = None,
    topic3: str | None = None,
    verified: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ImageAssetItem]:
    sql = """
        SELECT DISTINCT
            ia.asset_id,
            ia.filename,
            ia.file_path,
            ia.paper_id,
            ia.question_id,
            ia.source_id,
            ia.role,
            ia.sort_order,
            ia.mime_type,
            ia.width,
            ia.height,
            ia.description,
            ia.extracted_text,
            ia.image_type,
            ia.binding_confidence,
            ia.verified
        FROM image_assets ia
        LEFT JOIN papers p ON p.paper_id = ia.paper_id
        LEFT JOIN questions qn ON qn.question_id = ia.question_id
        WHERE (? IS NULL OR ia.paper_id = ?)
          AND (? IS NULL OR ia.question_id = ?)
          AND (? IS NULL OR p.year = ?)
          AND (? IS NULL OR p.region = ?)
          AND (? IS NULL OR p.exam_type = ?)
          AND (? IS NULL OR qn.topic3 = ?)
          AND (? IS NULL OR ia.verified = ?)
          AND (
              ? IS NULL
              OR ia.filename LIKE '%' || ? || '%'
              OR ia.description LIKE '%' || ? || '%'
              OR ia.extracted_text LIKE '%' || ? || '%'
          )
        ORDER BY ia.updated_at DESC, ia.asset_id DESC
        LIMIT ? OFFSET ?
    """
    verified_value = None if verified is None else int(verified)
    params = [
        paper_id,
        paper_id,
        question_id,
        question_id,
        year,
        year,
        region,
        region,
        exam_type,
        exam_type,
        topic3,
        topic3,
        verified_value,
        verified_value,
        q,
        q,
        q,
        q,
        limit,
        offset,
    ]
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [ImageAssetItem(**row_to_dict(row)) for row in rows]


@app.get("/knowledge-points", response_model=list[KnowledgePointItem])
def list_knowledge_points(
    topic1_id: str | None = None,
    topic1_name: str | None = None,
    topic2_id: str | None = None,
    topic2_name: str | None = None,
    q: str | None = Query(default=None, description="Search topic names and ids"),
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[KnowledgePointItem]:
    sql = """
        SELECT
            topic3_id,
            topic3_name,
            topic2_id,
            topic2_name,
            topic1_id,
            topic1_name,
            source_chapter,
            status,
            note
        FROM knowledge_points
        WHERE (? IS NULL OR topic1_id = ?)
          AND (? IS NULL OR topic1_name = ?)
          AND (? IS NULL OR topic2_id = ?)
          AND (? IS NULL OR topic2_name = ?)
          AND (? IS NULL OR status = ?)
          AND (
              ? IS NULL
              OR topic1_name LIKE '%' || ? || '%'
              OR topic2_name LIKE '%' || ? || '%'
              OR topic3_name LIKE '%' || ? || '%'
              OR topic1_id LIKE '%' || ? || '%'
              OR topic2_id LIKE '%' || ? || '%'
              OR topic3_id LIKE '%' || ? || '%'
          )
        ORDER BY topic1_id, topic2_id, topic3_id
        LIMIT ? OFFSET ?
    """
    params = [
        topic1_id,
        topic1_id,
        topic1_name,
        topic1_name,
        topic2_id,
        topic2_id,
        topic2_name,
        topic2_name,
        status,
        status,
        q,
        q,
        q,
        q,
        q,
        q,
        q,
        limit,
        offset,
    ]
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [KnowledgePointItem(**row_to_dict(row)) for row in rows]


@app.get("/knowledge-points/counts")
def knowledge_point_counts() -> dict[str, int]:
    """每个 topic3 关联的题目数量（含所有 rank），用于知识点树题量展示。"""
    sql = """
        SELECT topic3_id, COUNT(DISTINCT question_id) AS cnt
        FROM question_knowledge_points
        GROUP BY topic3_id
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql).fetchall()
    return {row["topic3_id"]: row["cnt"] for row in rows}


@app.get("/stats/questions")
def question_stats() -> dict[str, int]:
    """按审核状态统计题目数量。"""
    sql = "SELECT status, COUNT(*) AS cnt FROM questions GROUP BY status"
    with closing(get_connection()) as connection:
        rows = connection.execute(sql).fetchall()
    return {row["status"]: row["cnt"] for row in rows}


@app.get("/filters/facets", response_model=FilterFacets)
def get_filter_facets() -> FilterFacets:
    with closing(get_connection()) as connection:
        years = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year DESC"
            ).fetchall()
        ]
        regions = fetch_distinct_strings(connection, "SELECT DISTINCT region FROM papers ORDER BY region")
        exam_types = fetch_distinct_strings(connection, "SELECT DISTINCT exam_type FROM papers ORDER BY exam_type")
        modules = fetch_distinct_strings(connection, "SELECT DISTINCT module FROM questions ORDER BY module")
        topic1_ids = fetch_distinct_strings(connection, "SELECT DISTINCT topic1_id FROM knowledge_points ORDER BY topic1_id")
        topic1_values = fetch_distinct_strings(connection, "SELECT DISTINCT topic1_name FROM knowledge_points ORDER BY topic1_name")
        topic2_ids = fetch_distinct_strings(connection, "SELECT DISTINCT topic2_id FROM knowledge_points ORDER BY topic2_id")
        topic2_values = fetch_distinct_strings(connection, "SELECT DISTINCT topic2 FROM questions ORDER BY topic2")
        topic3_ids = fetch_distinct_strings(connection, "SELECT DISTINCT topic3_id FROM knowledge_points ORDER BY topic3_id")
        topic3_values = fetch_distinct_strings(connection, "SELECT DISTINCT topic3 FROM questions ORDER BY topic3")
        difficulties = fetch_distinct_strings(connection, "SELECT DISTINCT difficulty FROM questions ORDER BY difficulty")
        question_types = fetch_distinct_strings(connection, "SELECT DISTINCT question_type FROM questions ORDER BY question_type")
        statuses = fetch_distinct_strings(connection, "SELECT DISTINCT status FROM questions ORDER BY status")
    return FilterFacets(
        years=years,
        regions=regions,
        exam_types=exam_types,
        modules=modules,
        topic1_ids=topic1_ids,
        topic1_values=topic1_values,
        topic2_ids=topic2_ids,
        topic2_values=topic2_values,
        topic3_ids=topic3_ids,
        topic3_values=topic3_values,
        difficulties=difficulties,
        question_types=question_types,
        statuses=statuses,
    )


@app.get("/review-queue", response_model=list[ReviewQueueItem])
def list_review_queue(
    status: str | None = None,
    queue_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ReviewQueueItem]:
    sql = """
        SELECT
            review_id,
            entity_type,
            entity_id,
            queue_type,
            status,
            priority,
            reason,
            payload_json,
            created_at,
            updated_at
        FROM review_queue
        WHERE (? IS NULL OR status = ?)
          AND (? IS NULL OR queue_type = ?)
        ORDER BY priority ASC, created_at DESC
        LIMIT ? OFFSET ?
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, (status, status, queue_type, queue_type, limit, offset)).fetchall()
    return [ReviewQueueItem(**row_to_dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# Teacher review & import
# ---------------------------------------------------------------------------


class ReviewActionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    reason: str | None = None
    reviewer: str | None = None


class ReviewActionResponse(BaseModel):
    question_id: str
    action: str
    status: str
    review_id: str


@app.post("/questions/{question_id}/review", response_model=ReviewActionResponse)
def review_question(question_id: str, payload: ReviewActionRequest) -> ReviewActionResponse:
    """教师审核：approve 将题目置为已审核并留痕；reject 仅记录打回原因。"""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT question_id, status FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Question not found")
        current_status = row["status"]

        review_id = f"REV-{uuid.uuid4().hex[:12]}"
        if payload.action == "approve":
            new_status = "已审核"
            queue_status = "approved"
            connection.execute(
                "UPDATE questions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (new_status, question_id),
            )
        else:
            new_status = "已驳回"
            queue_status = "rejected"
            connection.execute(
                "UPDATE questions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (new_status, question_id),
            )

        connection.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status,
                priority, reason, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                review_id,
                "question",
                question_id,
                "teacher_review",
                queue_status,
                0,
                payload.reason,
                json.dumps(
                    {"reviewer": payload.reviewer, "action": payload.action},
                    ensure_ascii=False,
                ),
            ),
        )
        connection.commit()

    return ReviewActionResponse(
        question_id=question_id,
        action=payload.action,
        status=new_status,
        review_id=review_id,
    )


# ---------------------------------------------------------------------------
# Review closed-loop: AI propose-fix → human decide
# ---------------------------------------------------------------------------


class ProposeFixRequest(BaseModel):
    new_stem_text: str = Field(min_length=1)
    fix_type: str = "full"
    summary: str | None = None
    reason: str | None = None
    ai_source: str | None = None


class ProposeFixResponse(BaseModel):
    review_id: str
    question_id: str
    status: str


@app.post("/questions/{question_id}/propose-fix", response_model=ProposeFixResponse)
def propose_fix(question_id: str, payload: ProposeFixRequest) -> ProposeFixResponse:
    """AI 提交修改建议：写入 review_queue(pending)，不改题库，等人工定夺。"""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT question_id FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Question not found")

        review_id = f"REV-{uuid.uuid4().hex[:12]}"
        connection.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status,
                priority, reason, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'ai_fix', 'pending', 0, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                review_id,
                "question",
                question_id,
                payload.reason or payload.summary,
                json.dumps(
                    {
                        "new_stem_text": payload.new_stem_text,
                        "fix_type": payload.fix_type,
                        "summary": payload.summary,
                        "ai_source": payload.ai_source,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        connection.commit()
    return ProposeFixResponse(review_id=review_id, question_id=question_id, status="pending")


class PendingFixItem(BaseModel):
    review_id: str
    question_id: str
    fix_type: str | None = None
    summary: str | None = None
    reason: str | None = None
    ai_source: str | None = None
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    status: str | None = None
    created_at: str


@app.get("/review-queue/pending-fixes", response_model=list[PendingFixItem])
def list_pending_fixes() -> list[PendingFixItem]:
    """列出所有待人工定夺的 AI 修改建议。"""
    sql = """
        SELECT
            rq.review_id,
            rq.entity_id AS question_id,
            rq.reason,
            rq.payload_json,
            rq.created_at,
            q.module, q.topic2, q.topic3, q.status
        FROM review_queue rq
        LEFT JOIN questions q ON q.question_id = rq.entity_id
        WHERE rq.queue_type = 'ai_fix' AND rq.status = 'pending'
        ORDER BY rq.created_at DESC
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql).fetchall()
    items: list[PendingFixItem] = []
    for row in rows:
        d = row_to_dict(row)
        try:
            payload = json.loads(d.pop("payload_json", None) or "{}")
        except (json.JSONDecodeError, TypeError):
            payload = {}
        d["fix_type"] = payload.get("fix_type")
        d["summary"] = payload.get("summary")
        d["ai_source"] = payload.get("ai_source")
        items.append(PendingFixItem(**d))
    return items


class RejectedQuestionItem(BaseModel):
    question_id: str
    module: str | None = None
    topic2: str | None = None
    topic3: str | None = None
    status: str
    primary_paper_id: str | None = None
    primary_question_no: int | None = None
    vault_markdown_path: str | None = None
    latest_reason: str | None = None
    latest_queue_type: str | None = None
    latest_at: str | None = None
    pending_fix_count: int = 0


@app.get("/review-queue/rejected", response_model=list[RejectedQuestionItem])
def list_rejected_questions(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[RejectedQuestionItem]:
    """已驳回题目列表：带最新驳回原因 + 待审 AI 建议数。"""
    sql = """
        SELECT
            q.question_id, q.module, q.topic2, q.topic3, q.status,
            q.primary_paper_id, q.primary_question_no, q.vault_markdown_path,
            (
                SELECT rq.reason FROM review_queue rq
                WHERE rq.entity_id = q.question_id AND rq.entity_type = 'question'
                  AND rq.status IN ('rejected', 'pending')
                ORDER BY rq.created_at DESC LIMIT 1
            ) AS latest_reason,
            (
                SELECT rq.queue_type FROM review_queue rq
                WHERE rq.entity_id = q.question_id AND rq.entity_type = 'question'
                  AND rq.status IN ('rejected', 'pending')
                ORDER BY rq.created_at DESC LIMIT 1
            ) AS latest_queue_type,
            (
                SELECT rq.created_at FROM review_queue rq
                WHERE rq.entity_id = q.question_id AND rq.entity_type = 'question'
                  AND rq.status IN ('rejected', 'pending')
                ORDER BY rq.created_at DESC LIMIT 1
            ) AS latest_at,
            (
                SELECT COUNT(*) FROM review_queue rq
                WHERE rq.entity_id = q.question_id AND rq.entity_type = 'question'
                  AND rq.queue_type = 'ai_fix' AND rq.status = 'pending'
            ) AS pending_fix_count
        FROM questions q
        WHERE q.status = '已驳回'
        ORDER BY q.updated_at DESC
        LIMIT ? OFFSET ?
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, (limit, offset)).fetchall()
    return [RejectedQuestionItem(**row_to_dict(row)) for row in rows]


class FixDetailResponse(BaseModel):
    review_id: str
    question_id: str
    queue_type: str
    status: str
    reason: str | None = None
    fix_type: str | None = None
    summary: str | None = None
    ai_source: str | None = None
    current_stem_text: str | None = None
    new_stem_text: str | None = None
    created_at: str


@app.get("/review-queue/{review_id}", response_model=FixDetailResponse)
def get_fix_detail(review_id: str) -> FixDetailResponse:
    """查看单条 AI 建议详情：原题干 vs AI 建议新题干。"""
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT rq.review_id, rq.entity_id AS question_id, rq.queue_type, rq.status,
                   rq.reason, rq.payload_json, rq.created_at,
                   qti.stem_text AS current_stem_text
            FROM review_queue rq
            LEFT JOIN question_text_index qti ON qti.question_id = rq.entity_id
            WHERE rq.review_id = ?
            """,
            (review_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Review record not found")
    d = row_to_dict(row)
    try:
        payload = json.loads(d.pop("payload_json", None) or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}
    d["fix_type"] = payload.get("fix_type")
    d["summary"] = payload.get("summary")
    d["ai_source"] = payload.get("ai_source")
    d["new_stem_text"] = payload.get("new_stem_text")
    return FixDetailResponse(**d)


class DecideFixRequest(BaseModel):
    action: str = Field(pattern="^(apply|reject)$")
    reviewer: str | None = None
    reason: str | None = None


class DecideFixResponse(BaseModel):
    review_id: str
    question_id: str
    action: str
    question_status: str


@app.post("/review-queue/{review_id}/decide", response_model=DecideFixResponse)
def decide_fix(review_id: str, payload: DecideFixRequest) -> DecideFixResponse:
    """人工定夺 AI 建议：apply=应用修改入库并置已审核；reject=丢弃，题目保持已驳回。"""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT review_id, entity_id, status, payload_json FROM review_queue WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Review record not found")
        question_id = row["entity_id"]

        if payload.action == "apply":
            try:
                proposed = json.loads(row["payload_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                proposed = {}
            new_stem = proposed.get("new_stem_text")
            if not new_stem:
                raise HTTPException(status_code=400, detail="该建议缺少 new_stem_text，无法应用")
            connection.execute(
                "UPDATE question_text_index SET stem_text = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (new_stem, question_id),
            )
            connection.execute(
                "UPDATE questions SET status = '已审核', updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (question_id,),
            )
            connection.execute(
                "UPDATE review_queue SET status = 'applied', updated_at = CURRENT_TIMESTAMP WHERE review_id = ?",
                (review_id,),
            )
            new_q_status = "已审核"
        else:
            connection.execute(
                "UPDATE review_queue SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE review_id = ?",
                (review_id,),
            )
            new_q_status = "已驳回"
        connection.commit()
    return DecideFixResponse(
        review_id=review_id, question_id=question_id,
        action=payload.action, question_status=new_q_status,
    )


# ---------------------------------------------------------------------------
# Review closed-loop: issue report, history, rejected list
# ---------------------------------------------------------------------------


class ReportIssueRequest(BaseModel):
    issue_type: str = "content"
    description: str | None = None
    reporter: str | None = None


class ReportIssueResponse(BaseModel):
    review_id: str
    question_id: str
    status: str


@app.post("/questions/{question_id}/report-issue", response_model=ReportIssueResponse)
def report_issue(question_id: str, payload: ReportIssueRequest) -> ReportIssueResponse:
    """已审核题报告错误：置为已驳回，进 review_queue 等修复。"""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT question_id FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Question not found")

        review_id = f"REV-{uuid.uuid4().hex[:12]}"
        connection.execute(
            "UPDATE questions SET status = '已驳回', updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
            (question_id,),
        )
        connection.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status,
                priority, reason, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'issue_report', 'pending', 0, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                review_id,
                "question",
                question_id,
                payload.description,
                json.dumps(
                    {
                        "issue_type": payload.issue_type,
                        "description": payload.description,
                        "reporter": payload.reporter,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        connection.commit()
    return ReportIssueResponse(review_id=review_id, question_id=question_id, status="已驳回")


@app.get("/questions/{question_id}/review-history", response_model=list[ReviewQueueItem])
def get_review_history(question_id: str) -> list[ReviewQueueItem]:
    """查一题的全部审核历史（打回/AI建议/报错，按时间倒序）。"""
    sql = """
        SELECT review_id, entity_type, entity_id, queue_type, status,
               priority, reason, payload_json, created_at, updated_at
        FROM review_queue
        WHERE entity_type = 'question' AND entity_id = ?
        ORDER BY created_at DESC, review_id DESC
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, (question_id,)).fetchall()
    return [ReviewQueueItem(**row_to_dict(row)) for row in rows]


# ── Question Version History ─────────────────────────────────────────


class QuestionVersionSummary(BaseModel):
    version_id: str
    question_id: str
    version_number: int
    change_summary: str | None = None
    modified_by: str = "system"
    source: str = "manual"
    created_at: str


class QuestionVersionDetail(BaseModel):
    version_id: str
    question_id: str
    version_number: int
    snapshot: dict
    change_summary: str | None = None
    modified_by: str = "system"
    source: str = "manual"
    created_at: str


class VersionRollbackRequest(BaseModel):
    modified_by: str = "teacher"


@app.get(
    "/questions/{question_id}/versions",
    response_model=list[QuestionVersionSummary],
)
def list_question_versions(question_id: str) -> list[QuestionVersionSummary]:
    """列出某题的全部历史版本（最新在前）。"""
    from .repositories.question_write import QuestionWriteRepository
    repo = QuestionWriteRepository()
    try:
        versions = repo.list_versions(question_id)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="数据库不可用")
    return [QuestionVersionSummary(**v) for v in versions]


@app.get(
    "/questions/{question_id}/versions/{version_id}",
    response_model=QuestionVersionDetail,
)
def get_question_version(question_id: str, version_id: str) -> QuestionVersionDetail:
    """查看某个历史版本的完整快照。"""
    from .repositories.question_write import QuestionWriteRepository
    repo = QuestionWriteRepository()
    try:
        v = repo.get_version(version_id)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="数据库不可用")
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v["question_id"] != question_id:
        raise HTTPException(status_code=404, detail="版本不属于该题")
    return QuestionVersionDetail(**v)


@app.post(
    "/questions/{question_id}/versions/{version_id}/rollback",
    response_model=dict,
)
def rollback_question_version(
    question_id: str,
    version_id: str,
    body: VersionRollbackRequest | None = None,
) -> dict:
    """回退到指定历史版本。回退本身也会创建一条新的版本记录。"""
    import json
    from .repositories.question_write import _capture_version_snapshot
    from .services.question_write import QuestionWriteService

    repo = QuestionWriteRepository()
    try:
        v = repo.get_version(version_id)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="数据库不可用")

    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v["question_id"] != question_id:
        raise HTTPException(status_code=404, detail="版本不属于该题")

    snapshot = v["snapshot"]
    if not snapshot:
        raise HTTPException(status_code=400, detail="版本快照为空，无法回退")

    # Reconstruct question data from snapshot
    question_data = {
        "question_id": question_id,
        "question_type": snapshot.get("question_type", "calculation"),
        "title": snapshot.get("title", snapshot.get("stem_text", "").split("\n")[0] if snapshot.get("stem_text") else ""),
        "options": json.loads(snapshot.get("options_json", "[]")) if isinstance(snapshot.get("options_json"), str) else (snapshot.get("options_json") or []),
        "answer": snapshot.get("answer", ""),
        "analysis": snapshot.get("analysis", ""),
        "sub_questions": json.loads(snapshot.get("sub_questions_json", "[]")) if isinstance(snapshot.get("sub_questions_json"), str) else (snapshot.get("sub_questions_json") or []),
        "figures": [],
        "difficulty": snapshot.get("difficulty"),
        "knowledge_point": snapshot.get("knowledge_point", ""),
        "tags": json.loads(snapshot.get("tags_json", "[]")) if isinstance(snapshot.get("tags_json"), str) else [],
        "source": snapshot.get("source", ""),
        "review_status": "confirmed",
    }

    # Save as current (this triggers a new version snapshot via upsert_many)
    service = QuestionWriteService(repo)
    result = service.save_batch([question_data])

    if result.saved_count == 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "回退失败：无法写入数据库",
                "errors": result.errors,
            },
        )

    return {
        "ok": True,
        "question_id": question_id,
        "restored_from_version": version_id,
        "restored_version_number": v["version_number"],
        "message": f"已回退到版本 {v['version_number']}（{v.get('change_summary', '未知变更')}），并生成新的版本记录",
    }


class ImportQuestionRequest(BaseModel):
    classification: dict = Field(default_factory=dict)
    source: dict = Field(default_factory=dict)
    content: dict = Field(default_factory=dict)
    images: list[dict] = Field(default_factory=list)
    knowledge_points: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    reviewer: str | None = None
    note: str | None = None


class ImportQuestionResponse(BaseModel):
    question_id: str
    status: str
    knowledge_points_inserted: int
    images_linked: int
    skipped_knowledge_points: list[str] = Field(default_factory=list)
    review_id: str


@app.post("/questions/import", response_model=ImportQuestionResponse)
def import_question(payload: ImportQuestionRequest) -> ImportQuestionResponse:
    """导入外部 v2 JSON 新题：教师审核通过后写入数据库（status=已审核）。"""
    classification = payload.classification or {}
    source = payload.source or {}
    content = payload.content or {}
    metadata = payload.metadata or {}

    stem = (content.get("stem") or "").strip()
    if not stem:
        raise HTTPException(status_code=400, detail="content.stem is required")

    module = classification.get("module")
    topic2 = classification.get("topic2")
    topic3 = classification.get("topic3")
    question_type = classification.get("question_type")
    difficulty = classification.get("difficulty")
    paper_id = source.get("paper_id") or "IMPORT"
    question_no = source.get("question_no")

    text_parts = [stem]
    for opt in content.get("options") or []:
        text_parts.append(f"{opt.get('label', '')}. {opt.get('text', '')}")
    for sq in content.get("sub_questions") or []:
        text_parts.append(f"（{sq.get('index', '')}）{sq.get('stem', '')}")
    if content.get("answer"):
        text_parts.append(f"【答案】{content['answer']}")
    if content.get("analysis"):
        text_parts.append(f"【解析】{content['analysis']}")
    if content.get("tips"):
        text_parts.append(f"【点睛】{content['tips']}")
    full_text = "\n".join(text_parts)

    images = payload.images or []
    image_asset_ids = [img.get("asset_id") for img in images if img.get("asset_id")]
    image_filenames = [img.get("filename") for img in images if img.get("filename")]

    review_id = f"REV-{uuid.uuid4().hex[:12]}"

    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT MAX(CAST(SUBSTR(question_id, 2) AS INTEGER)) AS max_num FROM questions"
        ).fetchone()
        max_num = row["max_num"] or 0
        new_qid = f"Q{max_num + 1:08d}"

        canonical_title = f"第{question_no}题" if question_no else "导入题"
        markdown_path = metadata.get("vault_markdown_path") or f"import/{new_qid}.md"

        try:
            connection.execute(
                """
                INSERT INTO questions (
                    question_id, canonical_title, vault_markdown_path,
                    module, topic2, topic3, difficulty, question_type,
                    status, has_media, primary_paper_id, primary_question_no,
                    content_hash, schema_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    new_qid,
                    canonical_title,
                    markdown_path,
                    module,
                    topic2,
                    topic3,
                    str(difficulty) if difficulty is not None else None,
                    question_type,
                    "已审核",
                    1 if images else 0,
                    paper_id,
                    question_no,
                    None,
                    "v2",
                ),
            )

            connection.execute(
                """
                INSERT INTO question_text_index (
                    question_id, paper_id, source_id, question_no, markdown_path,
                    stem_text, image_asset_ids_json, image_filenames_json, image_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    new_qid,
                    paper_id,
                    metadata.get("source_id"),
                    question_no,
                    markdown_path,
                    full_text,
                    json.dumps(image_asset_ids, ensure_ascii=False),
                    json.dumps(image_filenames, ensure_ascii=False),
                    len(images),
                ),
            )

            kp_inserted = 0
            skipped_kps: list[str] = []
            for kp in payload.knowledge_points or []:
                topic3_id = kp.get("topic3_id")
                if not topic3_id:
                    continue
                exists = connection.execute(
                    "SELECT 1 FROM knowledge_points WHERE topic3_id = ?",
                    (topic3_id,),
                ).fetchone()
                if not exists:
                    skipped_kps.append(topic3_id)
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO question_knowledge_points (
                        question_id, rank, topic3_id, source, confidence, note,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        new_qid,
                        kp.get("rank", 1),
                        topic3_id,
                        kp.get("source") or "manual",
                        kp.get("confidence", 1.0),
                        kp.get("note"),
                    ),
                )
                kp_inserted += 1

            images_linked = 0
            for img in images:
                asset_id = img.get("asset_id")
                if not asset_id:
                    continue
                exists = connection.execute(
                    "SELECT 1 FROM image_assets WHERE asset_id = ?",
                    (asset_id,),
                ).fetchone()
                if not exists:
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO question_assets (
                        link_id, question_id, asset_id, placeholder_key, role,
                        sort_order, is_primary, is_verified, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"{new_qid}-{asset_id}",
                        new_qid,
                        asset_id,
                        img.get("placeholder_key"),
                        img.get("role") or "stem",
                        img.get("sort_order", 1),
                        1 if img.get("is_primary", True) else 0,
                        1 if img.get("verified", False) else 0,
                    ),
                )
                images_linked += 1

            connection.execute(
                """
                INSERT INTO review_queue (
                    review_id, entity_type, entity_id, queue_type, status,
                    priority, reason, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    review_id,
                    "question",
                    new_qid,
                    "import_approve",
                    "approved",
                    0,
                    payload.note,
                    json.dumps(
                        {"reviewer": payload.reviewer, "source": "external_import"},
                        ensure_ascii=False,
                    ),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    return ImportQuestionResponse(
        question_id=new_qid,
        status="已审核",
        knowledge_points_inserted=kp_inserted,
        images_linked=images_linked,
        skipped_knowledge_points=skipped_kps,
        review_id=review_id,
    )


@app.get("/processing-runs", response_model=list[ProcessingRunItem])
def list_processing_runs(
    pipeline_name: str | None = None,
    paper_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ProcessingRunItem]:
    sql = """
        SELECT
            run_id,
            pipeline_name,
            pipeline_version,
            paper_id,
            question_id,
            status,
            started_at,
            finished_at,
            operator,
            summary_json
        FROM processing_runs
        WHERE (? IS NULL OR pipeline_name = ?)
          AND (? IS NULL OR paper_id = ?)
          AND (? IS NULL OR status = ?)
        ORDER BY started_at DESC, run_id DESC
        LIMIT ? OFFSET ?
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(
            sql,
            (pipeline_name, pipeline_name, paper_id, paper_id, status, status, limit, offset),
        ).fetchall()
    return [ProcessingRunItem(**row_to_dict(row)) for row in rows]


@app.get("/embeddings/status", response_model=list[EmbeddingStatusItem])
def list_embedding_status() -> list[EmbeddingStatusItem]:
    sql = """
        SELECT
            model_name,
            model_version,
            vector_type,
            COUNT(*) AS owner_count,
            MAX(updated_at) AS last_updated_at
        FROM embeddings
        WHERE owner_type = 'question'
        GROUP BY model_name, model_version, vector_type
        ORDER BY owner_count DESC, model_name, vector_type
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(sql).fetchall()
    return [EmbeddingStatusItem(**row_to_dict(row)) for row in rows]


@app.post("/embeddings/questions/build", response_model=EmbeddingBuildResponse)
def build_question_embeddings(payload: EmbeddingBuildRequest) -> EmbeddingBuildResponse:
    provider = payload.provider.strip().lower()
    model_name = resolve_embedding_model(provider, payload.model)
    client = None if payload.dry_run else resolve_embedding_client(provider, payload.base_url)

    sql = """
        SELECT
            q.question_id,
            q.primary_paper_id AS paper_id,
            q.canonical_title,
            q.module,
            q.topic2,
            q.topic3,
            q.difficulty,
            q.question_type,
            qti.stem_text,
            q.vault_markdown_path
        FROM questions q
        INNER JOIN question_text_index qti ON qti.question_id = q.question_id
        WHERE qti.stem_text IS NOT NULL
          AND TRIM(qti.stem_text) != ''
    """
    params: list[Any] = []
    if payload.question_ids:
        placeholders = ",".join("?" for _ in payload.question_ids)
        sql += f" AND q.question_id IN ({placeholders})"
        params.extend(payload.question_ids)
    if payload.since_question_id:
        sql += " AND q.question_id >= ?"
        params.append(payload.since_question_id)
    sql += " ORDER BY q.question_id"
    if payload.limit:
        sql += " LIMIT ?"
        params.append(payload.limit)

    with closing(get_connection()) as connection:
        rows = connection.execute(sql, params).fetchall()
        existing_rows = connection.execute(
            """
            SELECT owner_id, content_hash
            FROM embeddings
            WHERE owner_type = 'question'
              AND model_name = ?
              AND COALESCE(model_version, '') = COALESCE(?, '')
              AND vector_type = ?
            """,
            (model_name, payload.model_version, payload.vector_type),
        ).fetchall()
        existing_hashes = {row["owner_id"]: row["content_hash"] for row in existing_rows}

        run_summary = {
            "provider": provider,
            "model_name": model_name,
            "model_version": payload.model_version,
            "vector_type": payload.vector_type,
            "candidate_count": len(rows),
            "dry_run": payload.dry_run,
        }
        run_id = create_processing_run(connection, run_summary)

        prepared: list[dict[str, Any]] = []
        skipped_count = 0
        for row in rows:
            trimmed_text, token_count = truncate_text(
                build_question_embedding_text(row),
                model_name,
                payload.max_tokens,
            )
            content_hash = compute_content_hash(trimmed_text)
            if not payload.force and existing_hashes.get(row["question_id"]) == content_hash:
                skipped_count += 1
                continue
            prepared.append(
                {
                    "question_id": row["question_id"],
                    "text": trimmed_text,
                    "token_count": token_count,
                    "content_hash": content_hash,
                }
            )

        embedded_count = 0
        errors: list[str] = []
        batch_size = payload.batch_size
        try:
            for start in range(0, len(prepared), batch_size):
                batch = prepared[start:start + batch_size]
                if payload.dry_run:
                    vectors = [None for _ in batch]
                else:
                    request_payload: dict[str, Any] = {
                        "model": model_name,
                        "input": [item["text"] for item in batch],
                        "encoding_format": "float",
                    }
                    if payload.dimensions:
                        request_payload["dimensions"] = payload.dimensions
                    response = client.embeddings.create(**request_payload)
                    vectors = [item.embedding for item in response.data]

                for index, item in enumerate(batch):
                    if payload.dry_run:
                        continue
                    vector = vectors[index]
                    upsert_question_embedding(
                        connection,
                        question_id=item["question_id"],
                        vector_type=payload.vector_type,
                        model_name=model_name,
                        model_version=payload.model_version,
                        dimensions=len(vector),
                        content_hash=item["content_hash"],
                        vector=vector,
                    )
                    embedded_count += 1

                if not payload.dry_run:
                    connection.commit()
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            errors.append(str(exc))
            finish_processing_run(
                connection,
                run_id,
                "failed",
                {
                    **run_summary,
                    "processed_count": len(prepared),
                    "embedded_count": embedded_count,
                    "skipped_count": skipped_count,
                    "errors": errors,
                },
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        finish_processing_run(
            connection,
            run_id,
            "completed",
            {
                **run_summary,
                "processed_count": len(prepared),
                "embedded_count": embedded_count,
                "skipped_count": skipped_count,
                "failed_count": len(errors),
            },
        )

    return EmbeddingBuildResponse(
        run_id=run_id,
        provider=provider,
        model_name=model_name,
        vector_type=payload.vector_type,
        processed_count=len(prepared),
        embedded_count=embedded_count,
        skipped_count=skipped_count,
        failed_count=len(errors),
        dry_run=payload.dry_run,
    )
