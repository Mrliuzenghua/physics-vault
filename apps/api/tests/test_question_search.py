"""Tests for the question search API and filter facets endpoint.

These tests explicitly enable the in-memory demo repository. Production
calls never fall back to demo questions unless PHYSICS_ALLOW_DEMO_DATA is set.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from physics_vault_api.app import create_app
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.question_search import (
    QuestionDatabaseUnavailableError,
    QuestionSearchRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_explicit_demo_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHYSICS_ALLOW_DEMO_DATA", "true")


def _client() -> TestClient:
    return TestClient(create_app())


def test_missing_database_never_returns_demo_data_unless_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("PHYSICS_ALLOW_DEMO_DATA", raising=False)
    repository = QuestionSearchRepository(str(tmp_path / "missing.sqlite3"))

    with pytest.raises(QuestionDatabaseUnavailableError, match="PHYSICS_DB_PATH"):
        repository.search_questions(search_mode="browse")


# ---------------------------------------------------------------------------
# GET /search/questions — browse (empty / default conditions)
# ---------------------------------------------------------------------------


def test_search_browse_returns_all_items() -> None:
    """Without any filters, browse mode returns all mock questions."""
    client = _client()
    response = client.get("/search/questions", params={"search_mode": "browse"})
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert "search_mode" in data
    assert "facets" in data

    assert data["total"] >= 1
    assert len(data["items"]) == data["total"]  # mock has 5 items, limit=20 default
    assert data["search_mode"] == "browse"


def test_search_browse_item_structure() -> None:
    """Each item in a browse response must contain all required fields."""
    client = _client()
    response = client.get("/search/questions", params={"search_mode": "browse"})
    assert response.status_code == 200

    data = response.json()
    item = data["items"][0]

    required_fields = {
        "question_id",
        "question_type",
        "title",
        "answer",
        "analysis",
        "options",
        "figures",
        "difficulty",
        "knowledge_point",
        "tags",
        "source",
        "year",
        "status",
        "knowledge_points",
        # Legacy-compat fields
        "canonical_title",
        "module",
        "topic2",
        "topic3",
        "primary_paper_id",
        "primary_question_no",
        "vault_markdown_path",
        "has_media",
        "image_count",
    }
    for field in required_fields:
        assert field in item, f"Field '{field}' missing from QuestionItem"


# ---------------------------------------------------------------------------
# GET /search/questions — keyword search (strict mode)
# ---------------------------------------------------------------------------


def test_search_strict_keyword_match() -> None:
    """Strict mode with a keyword should return items whose title/answer/analysis match."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "strict", "query": "牛顿"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["search_mode"] == "strict"
    assert data["total"] >= 1

    for item in data["items"]:
        keyword_match = (
            "牛顿" in (item.get("title") or "")
            or "牛顿" in (item.get("answer") or "")
            or "牛顿" in (item.get("analysis") or "")
        )
        assert keyword_match, f"Item {item['question_id']} does not contain keyword '牛顿'"


def test_strict_search_orders_fts_results_by_weighted_relevance(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "ranked-search.sqlite3")
    with sqlite3.connect(db_path) as conn:
        for question_id, title, tags in (
            ("q-title", "momentum conservation", "[]"),
            ("q-tag", "unrelated mechanics prompt", '["momentum"]'),
        ):
            conn.execute(
                "INSERT INTO questions (question_id, canonical_title, question_type, difficulty) VALUES (?, ?, 'calculation', 3)",
                (question_id, title),
            )
            conn.execute(
                "INSERT INTO question_text_index (question_id, title_text, stem_text, tags_json) VALUES (?, ?, ?, ?)",
                (question_id, title, title, tags),
            )

    rows, total = QuestionSearchRepository(str(db_path)).search_questions(
        search_mode="strict", query="momentum", limit=10
    )

    assert total == 2
    assert [row["question_id"] for row in rows] == ["q-title", "q-tag"]
    assert rows[0]["search_score"] >= rows[1]["search_score"]


def test_search_strict_no_query_returns_400() -> None:
    """Strict mode without a query should be rejected."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "strict"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /search/questions — filter by question type
# ---------------------------------------------------------------------------


def test_search_filter_by_question_type() -> None:
    """Filtering by question_type should return only matching items."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "question_type": "calculation"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["question_type"] == "calculation", (
            f"Expected calculation, got {item['question_type']}"
        )


def test_search_filter_by_question_type_no_results() -> None:
    """Filtering by a non-existent question_type returns empty results."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "question_type": "nonexistent_type"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# GET /search/questions — pagination
# ---------------------------------------------------------------------------


def test_search_pagination_limit() -> None:
    """limit parameter controls the number of items returned."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "limit": 2},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["limit"] == 2
    assert len(data["items"]) <= 2


def test_search_pagination_offset() -> None:
    """offset parameter skips the first N results."""
    client = _client()

    # Get first page
    page1 = client.get(
        "/search/questions",
        params={"search_mode": "browse", "limit": 2, "offset": 0},
    ).json()

    # Get second page
    page2 = client.get(
        "/search/questions",
        params={"search_mode": "browse", "limit": 2, "offset": 2},
    ).json()

    # Ensure no overlap between pages
    page1_ids = {item["question_id"] for item in page1["items"]}
    page2_ids = {item["question_id"] for item in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids), "Pages should not overlap"


def test_search_pagination_defaults() -> None:
    """Default limit and offset are 20 and 0."""
    client = _client()
    response = client.get("/search/questions", params={"search_mode": "browse"})
    data = response.json()
    assert data["limit"] == 20
    assert data["offset"] == 0


def test_search_limit_exceeds_max_returns_422() -> None:
    """limit > 200 should be rejected by FastAPI validation."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "limit": 999},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /search/questions — additional filters
# ---------------------------------------------------------------------------


def test_search_filter_by_difficulty() -> None:
    """Filtering by difficulty returns only matching items."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "difficulty": "5"},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["difficulty"] == "5"


def test_search_filter_by_status() -> None:
    """Filtering by status returns only matching items."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "status": "已审核"},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "已审核"


def test_search_filter_by_year() -> None:
    """Filtering by year returns only matching items."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "year": 2026},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["year"] == 2026


def test_search_filter_by_module() -> None:
    """Filtering by module returns only matching items."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "browse", "module": "力学"},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["module"] == "力学"


# ---------------------------------------------------------------------------
# GET /filters/facets
# ---------------------------------------------------------------------------


def test_facets_returns_structured_json() -> None:
    """The facets endpoint returns all required filter dimensions."""
    client = _client()
    response = client.get("/filters/facets")
    assert response.status_code == 200

    data = response.json()

    required_keys = {
        "years",
        "regions",
        "exam_types",
        "modules",
        "question_types",
        "difficulties",
        "statuses",
    }
    for key in required_keys:
        assert key in data, f"Key '{key}' missing from facets response"
        assert isinstance(data[key], list), f"Key '{key}' should be a list"


def test_facets_years_are_descending() -> None:
    """Years should be returned in descending order."""
    client = _client()
    response = client.get("/filters/facets")
    data = response.json()
    years = data["years"]
    assert years == sorted(years, reverse=True)


def test_facets_each_value_is_string_or_int() -> None:
    """All facet values should be consistently typed."""
    client = _client()
    response = client.get("/filters/facets")
    data = response.json()

    string_fields = {
        "regions",
        "exam_types",
        "modules",
        "question_types",
        "difficulties",
        "statuses",
    }
    for field in string_fields:
        for value in data[field]:
            assert isinstance(value, str), f"{field} value '{value}' should be str"

    for value in data["years"]:
        assert isinstance(value, int), f"years value '{value}' should be int"


# ---------------------------------------------------------------------------
# GET /search/questions — hybrid / similar degrade gracefully
# ---------------------------------------------------------------------------


def test_search_hybrid_degraded_to_strict() -> None:
    """hybrid mode should degrade to strict in v1 (no 500 error)."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "hybrid", "query": "电场"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["search_mode"] == "hybrid"
    assert data["total"] >= 0


def test_search_similar_degraded_to_strict() -> None:
    """similar mode should degrade to strict in v1 (no 500 error)."""
    client = _client()
    response = client.get(
        "/search/questions",
        params={"search_mode": "similar", "query": "动量"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["search_mode"] == "similar"
    assert data["total"] >= 0


# ---------------------------------------------------------------------------
# health still works
# ---------------------------------------------------------------------------


def test_health_still_works() -> None:
    """The existing /health endpoint must not be broken by the new router."""
    client = _client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
