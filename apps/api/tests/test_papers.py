from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.papers import PaperRepository
from physics_vault_api.routers.papers import build_papers_router
from physics_vault_api.services.papers import PaperService


def test_paper_list_and_detail_preserve_legacy_contract(tmp_path) -> None:
    db_path = tmp_path / "papers.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO papers (paper_id, year, exam_type, region, paper_name, subject, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("P-2026", 2026, "mock", "Shanghai", "Physics mock paper", "PHY", "structured"),
        )
        connection.executemany(
            "INSERT INTO questions (question_id, question_type, primary_paper_id) VALUES (?, ?, ?)",
            [("Q-1", "single_choice", "P-2026"), ("Q-2", "single_choice", "P-2026")],
        )
        connection.commit()

    app = FastAPI()
    app.include_router(build_papers_router(PaperService(PaperRepository(str(db_path)))))
    client = TestClient(app)

    listing = client.get("/papers", params={"q": "mock", "year": 2026})
    assert listing.status_code == 200
    assert listing.json()[0]["paper_id"] == "P-2026"
    assert listing.json()[0]["question_count"] == 2

    detail = client.get("/papers/P-2026")
    assert detail.status_code == 200
    assert detail.json()["paper_name"] == "Physics mock paper"
    assert detail.json()["question_count"] == 2

    paper_questions = client.get("/papers/P-2026/questions")
    assert paper_questions.status_code == 200
    assert [item["question_id"] for item in paper_questions.json()] == ["Q-1", "Q-2"]
    assert paper_questions.json()[0]["type"] == "single_choice"
    assert paper_questions.json()[0]["knowledge_points"] == []

    assert client.get("/papers/missing").status_code == 404
