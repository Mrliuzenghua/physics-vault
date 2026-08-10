"""Hybrid question retrieval backed by embeddings and DashScope reranking."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from ..repositories.question_search import QuestionSearchRepository
from .embedding_runtime import (
    default_alibaba_embedding_base_url,
    default_alibaba_rerank_url,
    resolve_dashscope_api_key,
    resolve_embedding_client,
    resolve_embedding_model,
)
from .retrieval_method_intent import (
    detect_method_intent,
    expand_method_query,
    score_method_candidate,
)
from .method_feature_index import ensure_method_feature_index_current

logger = logging.getLogger(__name__)


class SemanticSearchUnavailable(RuntimeError):
    """Raised when semantic retrieval has no usable vector index."""


@dataclass(frozen=True)
class SemanticSearchResult:
    rows: list[dict[str, Any]]
    total: int


@dataclass(frozen=True)
class _IndexEntry:
    owner_id: str
    vector: tuple[float, ...]
    norm: float


RerankTransport = Callable[[str, str, str, list[str], str], dict[int, float]]


class SemanticRetrievalService:
    """Recall with dense vectors, merge BM25 hits, then rerank candidates."""

    def __init__(
        self,
        repository: QuestionSearchRepository,
        *,
        embedding_client_factory: Callable[..., Any] = resolve_embedding_client,
        rerank_transport: RerankTransport | None = None,
    ) -> None:
        self._repo = repository
        self._embedding_client_factory = embedding_client_factory
        self._rerank_transport = rerank_transport or _dashscope_rerank
        self._index_cache: dict[
            tuple[str, str, str],
            tuple[tuple[int, str], list[_IndexEntry]],
        ] = {}

    def search(self, params: Any) -> SemanticSearchResult:
        query = str(params.query or "").strip()
        if not query:
            raise SemanticSearchUnavailable("semantic search requires a query")

        provider = os.getenv("PHYSICS_VAULT_EMBEDDING_PROVIDER", "openai").strip().lower()
        configured_model = os.getenv(
            "PHYSICS_VAULT_EMBEDDING_MODEL", "text-embedding-3-small"
        ).strip()
        model_name = resolve_embedding_model(provider, configured_model)
        model_version = os.getenv("PHYSICS_VAULT_EMBEDDING_MODEL_VERSION", "").strip()
        vector_type = os.getenv(
            "PHYSICS_VAULT_EMBEDDING_VECTOR_TYPE", "semantic_search"
        ).strip()
        candidate_limit = _bounded_int(
            os.getenv("PHYSICS_VAULT_RETRIEVAL_CANDIDATE_LIMIT", "80"),
            default=80,
            minimum=20,
            maximum=300,
        )

        index = self._load_index(
            model_name=model_name,
            model_version=model_version,
            vector_type=vector_type,
        )
        if not index:
            raise SemanticSearchUnavailable(
                f"no ready embeddings for {model_name}/{vector_type}"
            )

        filter_kwargs = _question_filters(params)
        allowed_rows, _ = self._repo.search_questions(
            search_mode="browse",
            query=None,
            limit=5000,
            offset=0,
            **filter_kwargs,
        )
        allowed_by_id = {str(row["question_id"]): row for row in allowed_rows}
        eligible_index = [entry for entry in index if entry.owner_id in allowed_by_id]
        if not eligible_index:
            raise SemanticSearchUnavailable("no indexed questions match the active filters")

        base_url = default_alibaba_embedding_base_url() if provider == "alibaba" else None
        client = self._embedding_client_factory(provider, base_url)
        dimensions = len(eligible_index[0].vector)
        method_intent = detect_method_intent(query)
        retrieval_query = expand_method_query(query, method_intent)
        response = client.embeddings.create(
            model=model_name,
            input=retrieval_query,
            encoding_format="float",
            dimensions=dimensions,
        )
        query_vector = tuple(float(value) for value in response.data[0].embedding)
        query_norm = math.sqrt(sum(value * value for value in query_vector))
        if not query_norm:
            raise SemanticSearchUnavailable("embedding provider returned a zero query vector")

        semantic_scores = {
            entry.owner_id: _cosine(query_vector, query_norm, entry)
            for entry in eligible_index
            if len(entry.vector) == len(query_vector)
        }
        semantic_ids = [
            question_id
            for question_id, _ in sorted(
                semantic_scores.items(), key=lambda item: item[1], reverse=True
            )[:candidate_limit]
        ]

        keyword_rows, _ = self._repo.search_questions(
            search_mode="strict",
            query=query,
            limit=candidate_limit,
            offset=0,
            **filter_kwargs,
        )
        keyword_scores = _normalise_keyword_scores(keyword_rows)

        method_matches: dict[str, dict[str, Any]] = {}
        if method_intent is not None:
            loader = getattr(self._repo, "load_method_features", None)
            indexed_rows: list[dict[str, Any]] | None = None
            if callable(loader):
                repository_db_path = getattr(self._repo, "db_path", None)
                if repository_db_path is not None:
                    ensure_method_feature_index_current(db_path=repository_db_path)
                indexed_rows = loader(
                    method_id=method_intent.method_id,
                    branches=method_intent.branches,
                )
            if indexed_rows is not None:
                level_rank = {"explicit": 3, "structural": 2, "related": 1}
                for feature in indexed_rows:
                    question_id = str(feature["question_id"])
                    if question_id not in allowed_by_id:
                        continue
                    try:
                        evidence = json.loads(str(feature.get("evidence_json") or "[]"))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        evidence = []
                    match = {
                        "method_id": str(feature["method_id"]),
                        "method_name": method_intent.method_name,
                        "branch": str(feature["branch"]),
                        "level": str(feature["level"]),
                        "match_basis": str(feature["match_basis"]),
                        "score": float(feature["score"]),
                        "evidence": evidence,
                    }
                    current = method_matches.get(question_id)
                    if current is None or (
                        level_rank.get(match["level"], 0),
                        match["score"],
                    ) > (
                        level_rank.get(str(current.get("level")), 0),
                        float(current.get("score") or 0),
                    ):
                        method_matches[question_id] = match
            else:
                for question_id, row in allowed_by_id.items():
                    match = score_method_candidate(query, row, intent=method_intent)
                    if match is not None:
                        method_matches[question_id] = match
        method_ids = [
            question_id
            for question_id, _ in sorted(
                method_matches.items(),
                key=lambda item: (
                    float(item[1]["score"]),
                    item[1]["level"] == "explicit",
                ),
                reverse=True,
            )[:candidate_limit]
        ]

        candidate_ids = list(
            dict.fromkeys(
                method_ids
                + semantic_ids
                + [str(row["question_id"]) for row in keyword_rows]
            )
        )
        candidate_ids = candidate_ids[: candidate_limit * 2]
        candidate_rows = [allowed_by_id[item] for item in candidate_ids if item in allowed_by_id]
        if not candidate_rows:
            raise SemanticSearchUnavailable("semantic and keyword recall returned no candidates")

        documents = [
            _question_document(row, include_analysis=method_intent is not None)
            for row in candidate_rows
        ]
        rerank_scores: dict[int, float] = {}
        rerank_url = default_alibaba_rerank_url()
        api_key = resolve_dashscope_api_key()
        rerank_model = os.getenv("PHYSICS_VAULT_RERANK_MODEL", "gte-rerank-v2").strip()
        if provider == "alibaba" and rerank_url and api_key and documents:
            try:
                rerank_scores = self._rerank_transport(
                    rerank_url,
                    api_key,
                    retrieval_query,
                    documents,
                    rerank_model,
                )
            except Exception as exc:
                logger.warning("DashScope rerank failed; using recall scores: %s", exc)

        mode = str(getattr(params.search_mode, "value", params.search_mode))
        ranked: list[dict[str, Any]] = []
        for index_position, row in enumerate(candidate_rows):
            question_id = str(row["question_id"])
            similarity = semantic_scores.get(question_id)
            semantic_score = _unit_cosine(similarity)
            keyword_score = keyword_scores.get(question_id, 0.0)
            knowledge_score = _knowledge_match(query, row)
            method_match = method_matches.get(question_id)
            method_score = float(method_match["score"]) if method_match else 0.0
            rerank_score = rerank_scores.get(index_position)
            if rerank_score is None:
                if method_intent is not None:
                    final_score = (
                        0.45 * semantic_score
                        + 0.20 * keyword_score
                        + 0.10 * knowledge_score
                        + 0.25 * method_score
                    )
                else:
                    final_score = (
                        0.95 * semantic_score + 0.05 * knowledge_score
                        if mode == "similar"
                        else 0.65 * semantic_score + 0.25 * keyword_score + 0.10 * knowledge_score
                    )
            elif mode == "similar":
                final_score = (
                    0.70 * _clamp(rerank_score)
                    + 0.25 * semantic_score
                    + 0.05 * knowledge_score
                )
            elif method_intent is not None:
                final_score = (
                    0.40 * _clamp(rerank_score)
                    + 0.20 * semantic_score
                    + 0.10 * keyword_score
                    + 0.05 * knowledge_score
                    + 0.25 * method_score
                )
            else:
                final_score = (
                    0.55 * _clamp(rerank_score)
                    + 0.25 * semantic_score
                    + 0.10 * keyword_score
                    + 0.10 * knowledge_score
                )

            payload = dict(row)
            payload["similarity"] = similarity
            payload["keyword_match"] = question_id in keyword_scores
            payload["search_score"] = final_score
            payload["rerank_score"] = rerank_score
            payload["method_match"] = method_match
            ranked.append(payload)

        ranked.sort(
            key=lambda row: (
                float(row.get("search_score") or 0.0),
                float(row.get("rerank_score") or 0.0),
                float(row.get("similarity") or -1.0),
            ),
            reverse=True,
        )
        total = len(ranked)
        return SemanticSearchResult(
            rows=ranked[params.offset : params.offset + params.limit],
            total=total,
        )

    def _load_index(
        self,
        *,
        model_name: str,
        model_version: str,
        vector_type: str,
    ) -> list[_IndexEntry]:
        cache_key = (model_name, model_version, vector_type)
        revision = self._repo.embedding_index_revision(
            model_name=model_name,
            model_version=model_version,
            vector_type=vector_type,
        )
        cached = self._index_cache.get(cache_key)
        if cached and cached[0] == revision:
            return cached[1]

        rows = self._repo.load_question_embeddings(
            model_name=model_name,
            model_version=model_version,
            vector_type=vector_type,
        )
        entries: list[_IndexEntry] = []
        for row in rows:
            try:
                values = json.loads(row.get("vector_json") or "[]")
                vector = tuple(float(value) for value in values)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            norm = math.sqrt(sum(value * value for value in vector))
            if vector and norm:
                entries.append(
                    _IndexEntry(owner_id=str(row["owner_id"]), vector=vector, norm=norm)
                )
        self._index_cache[cache_key] = (revision, entries)
        return entries


def _question_filters(params: Any) -> dict[str, Any]:
    return {
        key: getattr(params, key)
        for key in (
            "year",
            "module",
            "question_type",
            "difficulty",
            "status",
            "topic1_id",
            "topic2_id",
            "topic3_id",
            "topic2",
            "topic3",
            "region",
            "exam_type",
            "has_media",
            "image_count_min",
            "is_mistake",
        )
    }


def _question_document(row: dict[str, Any], *, include_analysis: bool = False) -> str:
    knowledge_names = [
        str(point.get("topic3_name") or "").strip()
        for point in (row.get("knowledge_points") or [])[:3]
        if isinstance(point, dict) and point.get("topic3_name")
    ]
    if include_analysis and row.get("analysis_text"):
        knowledge_names.append(f"解析方法：{row.get('analysis_text')}")
    parts = [
        f"标题：{row.get('title_text') or row.get('canonical_title') or ''}",
        f"题干：{row.get('stem_text') or ''}",
        f"三级知识点：{'、'.join(knowledge_names) or row.get('topic3') or ''}",
        f"模块：{row.get('module') or ''}",
        f"题型：{row.get('question_type') or ''}",
        f"难度：{row.get('difficulty') or ''}",
    ]
    return "\n".join(part for part in parts if not part.endswith("："))[:8000]


def _normalise_keyword_scores(rows: list[dict[str, Any]]) -> dict[str, float]:
    raw: dict[str, float] = {}
    for rank, row in enumerate(rows):
        try:
            value = float(row.get("search_score"))
        except (TypeError, ValueError):
            value = 1.0 / (rank + 1)
        raw[str(row["question_id"])] = max(value, 0.0)
    maximum = max(raw.values(), default=0.0)
    if maximum <= 0:
        return {question_id: 1.0 / (rank + 1) for rank, question_id in enumerate(raw)}
    return {question_id: value / maximum for question_id, value in raw.items()}


def _knowledge_match(query: str, row: dict[str, Any]) -> float:
    query_text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", query).casefold()
    if len(query_text) < 2:
        return 0.0
    labels = [
        str(point.get("topic3_name") or "")
        for point in (row.get("knowledge_points") or [])[:3]
        if isinstance(point, dict)
    ]
    labels.append(str(row.get("topic3") or ""))
    best = 0.0
    query_bigrams = {query_text[index : index + 2] for index in range(len(query_text) - 1)}
    for label in labels:
        clean_label = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", label).casefold()
        if len(clean_label) < 3:
            continue
        if clean_label in query_text or query_text in clean_label:
            best = max(best, 1.0)
            continue
        label_bigrams = {
            clean_label[index : index + 2] for index in range(len(clean_label) - 1)
        }
        if label_bigrams:
            best = max(best, len(query_bigrams & label_bigrams) / len(label_bigrams))
    return _clamp(best)


def _cosine(query_vector: tuple[float, ...], query_norm: float, entry: _IndexEntry) -> float:
    return sum(left * right for left, right in zip(query_vector, entry.vector)) / (
        query_norm * entry.norm
    )


def _unit_cosine(value: float | None) -> float:
    if value is None:
        return 0.0
    return _clamp((value + 1.0) / 2.0)


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _bounded_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _dashscope_rerank(
    url: str,
    api_key: str,
    query: str,
    documents: list[str],
    model: str,
) -> dict[int, float]:
    body = json.dumps(
        {
            "model": model,
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": False, "top_n": len(documents)},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"rerank HTTP {exc.code}: {detail}") from exc
    results = payload.get("output", {}).get("results", [])
    return {
        int(item["index"]): float(item["relevance_score"])
        for item in results
        if "index" in item and "relevance_score" in item
    }
