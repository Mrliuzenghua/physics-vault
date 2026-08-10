from __future__ import annotations

from fastapi.testclient import TestClient

from physics_vault_api.app import create_app
from physics_vault_api.services import lesson_reflections


def _reflection() -> dict:
    return {
        "id": "reflection-mcp-1",
        "projectId": "project-mcp-1",
        "projectTitle": "MCP 课后复盘",
        "rating": 4,
        "completed": True,
        "highlights": "完成度高",
        "followUp": "",
        "attendedPages": 8,
    }


def test_mcp_lesson_reflection_contract_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(lesson_reflections, "_STORE_FILE", tmp_path / "lesson-reflections.json")
    client = TestClient(create_app())

    created = client.post("/api/mcp/lesson-reflections", json={"reflection": _reflection()})
    assert created.status_code == 200
    assert created.json()["document_kind"] == "lesson_reflection"

    listed = client.get("/api/mcp/lesson-reflections?project_id=project-mcp-1")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == "reflection-mcp-1"

    loaded = client.get("/api/mcp/lesson-reflections/reflection-mcp-1")
    assert loaded.status_code == 200
    assert loaded.json()["reflection"]["completed"] is True
