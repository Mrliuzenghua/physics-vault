from __future__ import annotations

import sqlite3
import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from physics_vault_api.db_schema import initialize_database
from physics_vault_api.schemas.image_management import AddCachedImageRequest
from physics_vault_api.services.image_management import ImageManagementService


def _word_with_image() -> bytes:
    image_data = io.BytesIO()
    Image.new("RGB", (10, 8), "white").save(image_data, format="PNG")
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/media/image1.png", image_data.getvalue())
        archive.writestr("word/document.xml", "<document />")
    return document.getvalue()


def _question(db_path: Path, question_id: str = "Q-CACHE") -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO questions(question_id, question_type) VALUES (?, ?)",
            (question_id, "experiment"),
        )
        conn.execute(
            "INSERT INTO question_text_index(question_id, stem_text) VALUES (?, ?)",
            (question_id, "缓存图片测试题"),
        )


def test_cached_image_is_registered_bound_and_referenced(tmp_path: Path) -> None:
    db_path = tmp_path / "physics.sqlite3"
    initialize_database(db_path)
    _question(db_path)
    image_path = tmp_path / "data" / "import-batches" / "batch_demo" / "media" / "figure.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (24, 16), "white").save(image_path)

    service = ImageManagementService(db_path=str(db_path), root_path=str(tmp_path))
    result = service.add_cached_image(
        "Q-CACHE",
        AddCachedImageRequest(relative_path="data/import-batches/batch_demo/media/figure.png"),
    )

    assert result.asset_id.startswith("cache_")
    assert result.file_path == "data/import-batches/batch_demo/media/figure.png"
    with sqlite3.connect(db_path) as conn:
        asset = conn.execute("SELECT file_path FROM image_assets WHERE asset_id = ?", (result.asset_id,)).fetchone()
        link = conn.execute("SELECT placeholder_key FROM question_assets WHERE question_id = ?", ("Q-CACHE",)).fetchone()
        stem = conn.execute("SELECT stem_text FROM question_text_index WHERE question_id = ?", ("Q-CACHE",)).fetchone()[0]
    assert asset == (result.file_path,)
    assert link == (result.asset_id,)
    assert f"![fig:{result.asset_id}]" in stem


def test_cached_image_rejects_paths_outside_project(tmp_path: Path) -> None:
    db_path = tmp_path / "physics.sqlite3"
    initialize_database(db_path)
    _question(db_path)
    service = ImageManagementService(db_path=str(db_path), root_path=str(tmp_path))

    with pytest.raises(ValueError, match="超出项目目录"):
        service.add_cached_image("Q-CACHE", AddCachedImageRequest(relative_path="../outside.png"))


def test_temporary_cache_image_is_promoted_after_binding(tmp_path: Path) -> None:
    db_path = tmp_path / "physics.sqlite3"
    initialize_database(db_path)
    _question(db_path)
    cache_path = tmp_path / "data" / "cache" / "question-images" / "drop" / "figure.png"
    cache_path.parent.mkdir(parents=True)
    Image.new("RGB", (24, 16), "white").save(cache_path)

    service = ImageManagementService(db_path=str(db_path), root_path=str(tmp_path))
    result = service.add_cached_image(
        "Q-CACHE",
        AddCachedImageRequest(relative_path="data/cache/question-images/drop/figure.png"),
    )

    assert result.file_path.startswith("data/assets/questions/manual/")
    assert not cache_path.exists()
    assert (tmp_path / result.file_path).is_file()
    with sqlite3.connect(db_path) as conn:
        asset = conn.execute("SELECT file_path FROM image_assets WHERE asset_id = ?", (result.asset_id,)).fetchone()
    assert asset == (result.file_path,)


def test_word_drop_extracts_images_into_temporary_cache(tmp_path: Path) -> None:
    service = ImageManagementService(root_path=str(tmp_path))
    result = service.upload_cache_files([("lesson.docx", _word_with_image())])

    assert len(result.images) == 1
    assert result.images[0].relative_path.startswith("data/cache/question-images/")
    assert (tmp_path / result.images[0].relative_path).is_file()
