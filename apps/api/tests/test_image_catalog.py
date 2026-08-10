from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from physics_vault_api.application import _build_api_compatibility_router
from physics_vault_api.database import connect_db
from physics_vault_api.db_schema import initialize_database
from physics_vault_api.repositories.image_catalog import ImageCatalogRepository
from physics_vault_api.routers.image_catalog import build_image_catalog_router
from physics_vault_api.services.image_catalog import ImageCatalogService


def test_image_catalog_serves_canonical_and_legacy_compatibility_paths(tmp_path) -> None:
    db_path = tmp_path / "image-catalog.sqlite3"
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        connection.execute(
            "INSERT INTO questions (question_id, question_type) VALUES (?, ?)",
            ("Q-1", "single_choice"),
        )
        connection.execute(
            """
            INSERT INTO image_assets (asset_id, filename, file_path, question_id, verified)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("IMG-1", "force-diagram.png", "data/assets/questions/force-diagram.png", "Q-1", 1),
        )
        connection.execute(
            """
            INSERT INTO question_assets (link_id, question_id, asset_id, role, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("LINK-1", "Q-1", "IMG-1", "stem", 3),
        )
        connection.commit()

    router = build_image_catalog_router(ImageCatalogService(ImageCatalogRepository(str(db_path))))
    app = FastAPI()
    app.include_router(router)
    app.include_router(_build_api_compatibility_router(router))

    client = TestClient(app)
    response = client.get("/api/images", params={"q": "force", "verified": "true"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "asset_id": "IMG-1",
            "filename": "force-diagram.png",
            "file_path": "data/assets/questions/force-diagram.png",
            "paper_id": None,
            "question_id": "Q-1",
            "source_id": None,
            "role": "stem",
            "sort_order": 3,
            "mime_type": None,
            "width": None,
            "height": None,
            "description": None,
            "extracted_text": None,
            "image_type": None,
            "binding_confidence": None,
            "verified": True,
        }
    ]
    assert client.get("/images", params={"q": "force", "verified": "true"}).json() == response.json()
