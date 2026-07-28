from fastapi.testclient import TestClient

from physics_vault_api.app import create_app


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_clean_document_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/import/clean",
        json={
            "source_text": "第 1 页\n\n  题目一   \n\n\n题目二",
            "normalize_whitespace": True,
            "strip_headers_footers": True,
            "normalize_math_delimiters": True,
            "remove_blank_lines": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task"]["status"] == "completed"
    assert "cleaned_text" in data["task"]["result"]


def test_parse_structured_questions_endpoint() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/import/parse",
        json={
            "source_text": "1. 第一题\n题干内容\n2. 第二题\n题干内容",
            "import_batch_id": "batch-001",
            "source_type": "markdown",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task"]["status"] == "completed"
    assert data["task"]["result"]["question_count"] >= 2


# ── MCP-backed AI parse document tests ──


def test_ai_parse_document_mock_success() -> None:
    """POST /api/import/ai-parse-document succeeds in mock mode and returns structured questions."""
    client = TestClient(create_app())
    response = client.post(
        "/api/import/ai-parse-document",
        json={
            "batch_id": "batch-ai-001",
            "file_path": "/tmp/test_scan.pdf",
            "file_type": "pdf",
        },
    )
    assert response.status_code == 200
    data = response.json()
    task = data["task"]
    assert task["status"] == "completed"
    assert task["task_type"] == "ai_parse_document"
    assert task["result"]["document_type"] == "mock_pdf"
    assert task["result"]["question_count"] >= 1
    assert len(task["result"]["questions"]) >= 1
    # Verify question structure
    q = task["result"]["questions"][0]
    assert "question_id" in q
    assert "title" in q
    assert "question_type" in q
    assert "confidence" in q


def test_ai_parse_document_polling() -> None:
    """The AI parse task can be polled via GET /api/import/tasks/{task_id}."""
    client = TestClient(create_app())
    response = client.post(
        "/api/import/ai-parse-document",
        json={
            "batch_id": "batch-ai-002",
            "file_path": "/tmp/test.jpg",
            "file_type": "jpg",
        },
    )
    task_id = response.json()["task"]["task_id"]

    polled = client.get(f"/api/import/tasks/{task_id}")
    assert polled.status_code == 200
    assert polled.json()["status"] == "completed"
    assert polled.json()["task_type"] == "ai_parse_document"


def test_ai_parse_document_with_all_options() -> None:
    """AI parse respects optional flags (preprocess, region detection, etc.)."""
    client = TestClient(create_app())
    response = client.post(
        "/api/import/ai-parse-document",
        json={
            "batch_id": "batch-ai-003",
            "file_path": "/tmp/test.png",
            "file_type": "png",
            "mode": "image_document",
            "enable_preprocess": False,
            "enable_region_detection": True,
            "enable_figure_extraction": False,
            "enable_table_extraction": False,
            "formula_format": "latex",
            "ignore_headers_footers": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["task"]["status"] == "completed"
