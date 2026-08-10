from __future__ import annotations

import json
from types import SimpleNamespace

from physics_vault_api.schemas.question_search import QuestionSearchParams, SearchMode
from physics_vault_api.services.semantic_retrieval import SemanticRetrievalService


class _FakeRepository:
    def __init__(self) -> None:
        self.rows = [
            {
                "question_id": "q-keyword",
                "canonical_title": "Momentum conservation",
                "stem_text": "Two carts collide.",
                "knowledge_points": [{"topic3_name": "动量守恒"}],
            },
            {
                "question_id": "q-semantic",
                "canonical_title": "Collision reasoning",
                "stem_text": "Find the shared velocity after impact.",
                "knowledge_points": [{"topic3_name": "碰撞"}],
            },
            {
                "question_id": "q-other",
                "canonical_title": "Electric field",
                "stem_text": "Find the field strength.",
                "knowledge_points": [{"topic3_name": "电场强度"}],
            },
        ]

    def embedding_index_revision(self, **_: object) -> tuple[int, str]:
        return 3, "2026-08-08"

    def load_question_embeddings(self, **_: object) -> list[dict[str, object]]:
        return [
            {"owner_id": "q-keyword", "vector_json": json.dumps([0.95, 0.05])},
            {"owner_id": "q-semantic", "vector_json": json.dumps([0.90, 0.10])},
            {"owner_id": "q-other", "vector_json": json.dumps([0.0, 1.0])},
        ]

    def search_questions(self, *, search_mode: str, **_: object):
        if search_mode == "strict":
            return [{**self.rows[0], "search_score": 2.0}], 1
        return list(self.rows), len(self.rows)


class _FakeEmbeddings:
    @staticmethod
    def create(**_: object) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, 0.0])])


class _FakeClient:
    embeddings = _FakeEmbeddings()


def test_hybrid_retrieval_merges_embedding_keyword_and_rerank(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_VAULT_EMBEDDING_PROVIDER", "alibaba")
    monkeypatch.setenv("PHYSICS_VAULT_EMBEDDING_MODEL", "text-embedding-v3")
    monkeypatch.setenv("PHYSICS_VAULT_EMBEDDING_VECTOR_TYPE", "semantic_search")

    service = SemanticRetrievalService(
        _FakeRepository(),
        embedding_client_factory=lambda *_: _FakeClient(),
        rerank_transport=lambda *_: {0: 0.70, 1: 0.98, 2: 0.01},
    )
    result = service.search(
        QuestionSearchParams(
            search_mode=SearchMode.hybrid,
            query="碰撞后共同速度",
            limit=3,
        )
    )

    assert [row["question_id"] for row in result.rows] == [
        "q-semantic",
        "q-keyword",
        "q-other",
    ]
    assert result.rows[0]["similarity"] > 0.9
    assert result.rows[1]["keyword_match"] is True
    assert result.rows[0]["search_score"] > result.rows[1]["search_score"]
