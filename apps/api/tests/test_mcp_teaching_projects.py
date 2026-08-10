from __future__ import annotations

from fastapi.testclient import TestClient

from physics_vault_api.app import create_app
from physics_vault_api.services import teaching_projects


def _project() -> dict:
    return {
        "id": "project-mcp-1",
        "title": "MCP 课堂项目",
        "projectType": "lesson",
        "contentRevision": 1,
        "content": {"meta": {"title": "MCP 课堂项目"}, "nodes": []},
        "handout": {"id": "handout-mcp-1", "status": "draft", "sourceRevision": 1},
        "slides": {"id": "slides-mcp-1", "status": "draft", "sourceRevision": 1},
    }


def test_mcp_teaching_project_contract_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(teaching_projects, "_STORE_FILE", tmp_path / "teaching-projects.json")
    client = TestClient(create_app())

    created = client.post("/api/mcp/teaching-projects", json={"project": _project()})
    assert created.status_code == 200
    assert created.json()["document_kind"] == "teaching_project"

    listed = client.get("/api/mcp/teaching-projects")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == "project-mcp-1"

    loaded = client.get("/api/mcp/teaching-projects/project-mcp-1")
    assert loaded.status_code == 200
    assert loaded.json()["summary"]["contentRevision"] == 1
