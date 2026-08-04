import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from physics_vault_api.app import create_app
from physics_vault_api.config import McpSettings
from physics_vault_api.routers import mcp as mcp_router
from physics_vault_api.runtime_config import AiServiceConfig, RuntimeAiConfig
from physics_vault_api.services.mcp_gateway import McpGatewayService


def _make_client(**env_overrides: str) -> TestClient:
    """Create a TestClient with controlled env vars."""
    with patch.dict(os.environ, {**os.environ, **env_overrides}, clear=False):
        return TestClient(create_app())


def test_mcp_status_structure() -> None:
    """GET /api/mcp/status returns all required fields with correct types."""
    client = _make_client(PHYSICS_MCP_MODE="mock", PHYSICS_AI_ENABLED="true")
    response = client.get("/api/mcp/status")

    assert response.status_code == 200
    payload = response.json()

    # Required fields
    assert isinstance(payload["enabled"], bool)
    assert payload["mode"] in {"mock", "disabled", "stdio"}
    assert isinstance(payload["working_directory"], str)
    assert isinstance(payload["tools"], dict)

    # Tools dict must contain all 6 keys
    expected_tools = {
        "parse_document",
        "detect_question_regions",
        "parse_question_region",
        "generate_analysis",
        "generate_knowledge",
        "generate_metadata",
    }
    assert set(payload["tools"].keys()) == expected_tools

    # New fields
    assert isinstance(payload["vl_available"], bool)
    assert isinstance(payload["llm_available"], bool)
    assert payload["last_checked_at"] is not None


def test_test_connection_mock_vl() -> None:
    """POST /api/mcp/test-connection succeeds for VL in mock mode."""
    client = _make_client(PHYSICS_MCP_MODE="mock", PHYSICS_AI_ENABLED="true")
    response = client.post("/api/mcp/test-connection", json={"target": "vl"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["target"] == "vl"
    assert payload["mode"] == "mock"
    assert payload["reachable"] is True
    assert "mock" in payload["message"].lower()


def test_test_connection_mock_llm() -> None:
    """POST /api/mcp/test-connection succeeds for LLM in mock mode."""
    client = _make_client(PHYSICS_MCP_MODE="mock", PHYSICS_AI_ENABLED="true")
    response = client.post("/api/mcp/test-connection", json={"target": "llm"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["target"] == "llm"
    assert payload["mode"] == "mock"
    assert payload["reachable"] is True


def test_test_connection_disabled() -> None:
    """POST /api/mcp/test-connection returns unreachable when AI is disabled."""
    client = _make_client(PHYSICS_MCP_MODE="mock", PHYSICS_AI_ENABLED="false")
    response = client.post("/api/mcp/test-connection", json={"target": "llm"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "disabled"
    assert payload["reachable"] is False
    assert "disabled" in payload["message"].lower() or "disable" in payload["message"].lower()


def test_test_connection_invalid_target() -> None:
    """POST /api/mcp/test-connection rejects invalid target values."""
    client = _make_client(PHYSICS_MCP_MODE="mock", PHYSICS_AI_ENABLED="true")

    # Invalid target string
    response = client.post("/api/mcp/test-connection", json={"target": "invalid"})
    assert response.status_code == 422  # Pydantic validation error

    # Missing target field
    response = client.post("/api/mcp/test-connection", json={})
    assert response.status_code == 422


def test_runtime_config_never_returns_saved_api_keys(monkeypatch) -> None:
    runtime = RuntimeAiConfig(
        vl=AiServiceConfig(base_url="https://vl.example", api_key="vl-secret", model_name="vl-model"),
        llm=AiServiceConfig(base_url="https://llm.example", api_key="llm-secret", model_name="llm-model"),
    )
    monkeypatch.setattr(mcp_router, "get_runtime_config", lambda: runtime)

    response = TestClient(create_app()).get("/api/mcp/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vl_configured"] is True
    assert payload["llm_configured"] is True
    assert payload["vl"]["api_key"] == ""
    assert payload["llm"]["api_key"] == ""
    assert "vl-secret" not in response.text
    assert "llm-secret" not in response.text


def test_chat_test_validates_role_and_temperature_before_provider_call() -> None:
    client = TestClient(create_app())

    invalid_role = client.post(
        "/api/mcp/chat-test",
        json={"messages": [{"role": "tool", "content": "hello"}]},
    )
    invalid_temperature = client.post(
        "/api/mcp/chat-test",
        json={"messages": [{"role": "user", "content": "hello"}], "temperature": 9},
    )

    assert invalid_role.status_code == 422
    assert invalid_temperature.status_code == 422

    # Empty body
    response = client.post("/api/mcp/test-connection")
    assert response.status_code == 422


def test_test_connection_stdio_unconfigured() -> None:
    """POST /api/mcp/test-connection returns unreachable when stdio command is empty."""
    client = _make_client(
        PHYSICS_MCP_MODE="stdio",
        PHYSICS_AI_ENABLED="true",
        PHYSICS_MCP_VL_COMMAND="",
        PHYSICS_MCP_LLM_COMMAND="",
    )
    response = client.post("/api/mcp/test-connection", json={"target": "vl"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "stdio"
    assert payload["reachable"] is False
    assert "not configured" in payload["message"].lower() or "empty" in payload["message"].lower()


def test_mcp_status_endpoint() -> None:
    """Legacy test — ensure existing tests still pass."""
    client = TestClient(create_app())
    response = client.get("/api/mcp/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] in {"mock", "disabled", "stdio"}
    assert "generate_analysis" in payload["tools"]


def test_generate_analysis_mock_endpoint() -> None:
    """Legacy test — ensure generate_analysis still works."""
    client = TestClient(create_app())
    response = client.post(
        "/api/mcp/generate-analysis",
        json={
            "question": {
                "question_id": "q_001",
                "question_type": "calculation",
                "title": u"已知物体做匀加速直线运动，求其加速度。",
                "options": [],
                "answer": "",
                "analysis": "",
                "sub_questions": [],
                "figures": [],
                "tags": [],
            },
            "style": "classroom_brief",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["question_id"] == "q_001"


def test_http_metadata_result_maps_question_id_to_item_id() -> None:
    class FakeHttpClient:
        def generate_metadata(self, **_kwargs):
            return {
                "items": [
                    {"question_id": "q_001", "tags": ["力学"]},
                    {"question_id": "q_002", "source": "月考"},
                ]
            }

    service = McpGatewayService(McpSettings(mode="mock"))
    service._http_client = FakeHttpClient()

    import asyncio

    result = asyncio.run(
        service.generate_metadata(
            {
                "items": [
                    {"id": "q_001", "question": {"title": "题目一"}},
                    {"id": "q_002", "question": {"title": "题目二"}},
                ],
                "fields": ["tags", "source"],
                "constraints": {},
            }
        )
    )

    assert result["items"] == [
        {"id": "q_001", "tags": ["力学"]},
        {"id": "q_002", "source": "月考"},
    ]
