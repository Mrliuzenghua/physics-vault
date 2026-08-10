from __future__ import annotations

import sqlite3
import subprocess
from shutil import which
from pathlib import Path

from physics_vault_api.services.typst_exports import TypstQuestionExportService


def _create_export_source(db_path: Path, project_dir: Path) -> Path:
    image_path = project_dir / "data" / "assets" / "questions" / "diagram.svg"
    image_path.parent.mkdir(parents=True)
    image_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>',
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE questions (question_id TEXT PRIMARY KEY, canonical_title TEXT, question_type TEXT);
            CREATE TABLE question_text_index (
                question_id TEXT PRIMARY KEY, title_text TEXT, stem_text TEXT,
                options_json TEXT, figures_json TEXT, answer_text TEXT, analysis_text TEXT
            );
            CREATE TABLE image_assets (asset_id TEXT PRIMARY KEY, filename TEXT, file_path TEXT, question_id TEXT);
            CREATE TABLE question_assets (
                link_id TEXT PRIMARY KEY, question_id TEXT, asset_id TEXT, sort_order INTEGER
            );
            """
        )
        connection.execute("INSERT INTO questions VALUES (?, ?, ?)", ("Q00003593", "动能定理", "calculation"))
        connection.execute(
            "INSERT INTO question_text_index VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Q00003593", "动能定理", "如图求物体速度。", '[{"label":"A","text":"1 m/s"}]', "[]", "A", "由动能定理可得。"),
        )
        connection.execute(
            "INSERT INTO image_assets VALUES (?, ?, ?, ?)",
            ("IMG-1", "diagram.svg", "data/assets/questions/diagram.svg", "Q00003593"),
        )
        connection.execute("INSERT INTO question_assets VALUES (?, ?, ?, ?)", ("LINK-1", "Q00003593", "IMG-1", 0))
    return image_path


def test_typst_export_previews_then_writes_only_an_isolated_bundle(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    db_path = tmp_path / "questions.sqlite3"
    source_image = _create_export_source(db_path, project_dir)
    before_bytes = source_image.read_bytes()
    before_mtime = source_image.stat().st_mtime_ns
    service = TypstQuestionExportService(
        db_path=db_path,
        export_dir=project_dir / "data" / "exports",
        project_dir=project_dir,
    )

    preview = service.export(["Q00003593"], title="测试学案")

    assert preview["dry_run"] is True
    assert preview["planned_files"] == ["questions-data.typ", "image-map.typ"]
    assert not Path(preview["output_dir"]).exists()
    assert preview["gallery_policy"] == "read_only_reference_no_copy_move_rename_or_delete"
    assert source_image.read_bytes() == before_bytes
    assert source_image.stat().st_mtime_ns == before_mtime

    result = service.export(["Q00003593"], title="测试学案", include_answers=True, dry_run=False)
    output_dir = Path(result["output_dir"])
    typst_data = (output_dir / "questions-data.typ").read_text(encoding="utf-8")

    image_map = (output_dir / "image-map.typ").read_text(encoding="utf-8")
    assert {path.name for path in output_dir.iterdir()} == {"questions-data.typ", "image-map.typ"}
    assert not (output_dir / "_template.typ").exists()
    assert "#let question-data" in typst_data
    assert "#let figure-paths" in image_map
    assert "#let figures-for(question_id)" in image_map
    assert "../../../assets/questions/diagram.svg" in image_map
    assert "question_id: \"Q00003593\"" in typst_data
    assert "label: \"A\"" in typst_data
    assert source_image.read_bytes() == before_bytes
    assert source_image.stat().st_mtime_ns == before_mtime

    typst = which("typst")
    if typst:
        consumer = output_dir / "consumer.typ"
        consumer.write_text(
            '#import "questions-data.typ": question-data\n'
            '#import "image-map.typ": figures-for\n'
            "#let first = question-data.at(0)\n"
            "#text(first.stem)\n"
            "#image(figures-for(first.question_id).at(0), width: 1cm)\n",
            encoding="utf-8",
        )
        subprocess.run(
            [typst, "compile", "--root", str(project_dir), str(consumer)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert (output_dir / "consumer.pdf").is_file()
