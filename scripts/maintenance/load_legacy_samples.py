from __future__ import annotations

import json
import mimetypes
import shutil
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
TARGET_DB = PROJECT_ROOT / "data" / "app-db" / "physics_vault.sqlite3"
TARGET_ASSETS_DIR = PROJECT_ROOT / "data" / "assets" / "questions"
IMPORT_BATCH_ID = "LEGACY-SAMPLE-20260726"
SAMPLE_QUESTION_IDS = [
    "Q00000001",
    "Q00000004",
    "Q00000005",
    "Q00000006",
    "Q00000007",
    "Q00000009",
    "Q00000012",
    "Q00000013",
    "Q00000015",
    "Q00000017",
    "Q00000019",
    "Q00000022",
]


def find_old_db() -> Path:
    matches = list(WORKSPACE_ROOT.glob("02-*/01-db/physics_vault.sqlite3"))
    if not matches:
        raise FileNotFoundError("未找到旧数据库 physics_vault.sqlite3")
    return matches[0]


def find_old_image_dir() -> Path:
    matches = list(WORKSPACE_ROOT.glob("02-*/02-*"))
    if not matches:
        raise FileNotFoundError("未找到旧图片资源目录")
    return matches[0]


def review_status_from_status(status: str | None) -> str:
    if not status:
        return "parsed"
    if "审核" in status:
        return "approved"
    if "驳回" in status:
        return "rejected"
    if "校对" in status:
        return "reviewing"
    return "parsed"


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def load_rows(conn: sqlite3.Connection, sql: str, params=()) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, params).fetchall()


def main() -> int:
    old_db = find_old_db()
    old_images_dir = find_old_image_dir()
    TARGET_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(old_db)) as source_conn, sqlite3.connect(str(TARGET_DB)) as target_conn:
        source_conn.row_factory = sqlite3.Row
        target_conn.row_factory = sqlite3.Row
        target_conn.execute("PRAGMA foreign_keys = ON")

        placeholders = ",".join("?" for _ in SAMPLE_QUESTION_IDS)

        questions = load_rows(
            source_conn,
            f"""
            SELECT q.*, qti.paper_id, qti.source_id, qti.question_no, qti.markdown_path,
                   qti.stem_text, qti.image_asset_ids_json, qti.image_filenames_json,
                   qti.image_count, qti.answer_text, qti.analysis_text, qti.tips_text,
                   qti.options_json, qti.stem_clean_text, qti.tags_json, qti.source_text
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            WHERE q.question_id IN ({placeholders})
            ORDER BY q.question_id
            """,
            SAMPLE_QUESTION_IDS,
        )
        if not questions:
            raise RuntimeError("旧库里没有找到指定样例题")

        paper_ids = sorted({row["primary_paper_id"] for row in questions if row["primary_paper_id"]})
        paper_placeholders = ",".join("?" for _ in paper_ids) or "''"
        papers = load_rows(
            source_conn,
            f"SELECT * FROM papers WHERE paper_id IN ({paper_placeholders})",
            paper_ids,
        )

        question_sources = load_rows(
            source_conn,
            f"SELECT * FROM question_sources WHERE question_id IN ({placeholders})",
            SAMPLE_QUESTION_IDS,
        )
        kp_links = load_rows(
            source_conn,
            f"SELECT * FROM question_knowledge_points WHERE question_id IN ({placeholders})",
            SAMPLE_QUESTION_IDS,
        )
        topic3_ids = sorted({row["topic3_id"] for row in kp_links})
        kp_placeholders = ",".join("?" for _ in topic3_ids) or "''"
        knowledge_points = load_rows(
            source_conn,
            f"SELECT * FROM knowledge_points WHERE topic3_id IN ({kp_placeholders})",
            topic3_ids,
        )
        question_assets = load_rows(
            source_conn,
            f"SELECT * FROM question_assets WHERE question_id IN ({placeholders})",
            SAMPLE_QUESTION_IDS,
        )
        asset_ids = sorted({row["asset_id"] for row in question_assets})
        asset_placeholders = ",".join("?" for _ in asset_ids) or "''"
        image_assets = load_rows(
            source_conn,
            f"SELECT * FROM image_assets WHERE asset_id IN ({asset_placeholders})",
            asset_ids,
        )

        target_conn.execute(
            """
            INSERT INTO import_batches (
                import_batch_id, batch_name, source_type, source_path, pipeline_mode,
                status, total_files, total_questions, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(import_batch_id) DO UPDATE SET
                batch_name = excluded.batch_name,
                source_type = excluded.source_type,
                source_path = excluded.source_path,
                pipeline_mode = excluded.pipeline_mode,
                status = excluded.status,
                total_files = excluded.total_files,
                total_questions = excluded.total_questions,
                note = excluded.note,
                updated_at = datetime('now')
            """,
            (
                IMPORT_BATCH_ID,
                "旧库样例数据",
                "legacy_db",
                str(old_db),
                "manual_seed",
                "imported",
                len(asset_ids),
                len(questions),
                "从旧数据库抽取的一批演示题目与图片",
            ),
        )

        for qid in SAMPLE_QUESTION_IDS:
            target_conn.execute("DELETE FROM favorite_items WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM question_annotations WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM question_versions WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM review_queue WHERE entity_id = ?", (qid,))
            target_conn.execute("DELETE FROM question_assets WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM question_knowledge_points WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM question_sources WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM question_text_index WHERE question_id = ?", (qid,))
            target_conn.execute("DELETE FROM questions WHERE question_id = ?", (qid,))

        for row in papers:
            target_conn.execute(
                """
                INSERT INTO papers (
                    paper_id, year, exam_type, region, paper_name, subject,
                    source_path, source_format, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    year = excluded.year,
                    exam_type = excluded.exam_type,
                    region = excluded.region,
                    paper_name = excluded.paper_name,
                    subject = excluded.subject,
                    source_path = excluded.source_path,
                    source_format = excluded.source_format,
                    status = excluded.status,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    row["paper_id"], row["year"], row["exam_type"], row["region"], row["paper_name"], row["subject"],
                    row["source_path"], row["source_format"], row["status"], row["notes"], row["created_at"], row["updated_at"],
                ),
            )

        for row in knowledge_points:
            target_conn.execute(
                """
                INSERT INTO knowledge_points (
                    topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name,
                    source_chapter, status, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic3_id) DO UPDATE SET
                    topic3_name = excluded.topic3_name,
                    topic2_id = excluded.topic2_id,
                    topic2_name = excluded.topic2_name,
                    topic1_id = excluded.topic1_id,
                    topic1_name = excluded.topic1_name,
                    source_chapter = excluded.source_chapter,
                    status = excluded.status,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    row["topic3_id"], row["topic3_name"], row["topic2_id"], row["topic2_name"], row["topic1_id"], row["topic1_name"],
                    row["source_chapter"], row["status"], row["note"], row["created_at"], row["updated_at"],
                ),
            )

        image_by_asset = {row["asset_id"]: row for row in image_assets}
        assets_by_question: dict[str, list[sqlite3.Row]] = {}
        for row in question_assets:
            assets_by_question.setdefault(row["question_id"], []).append(row)

        copied_assets: set[str] = set()
        copied_asset_meta: dict[str, tuple[str, int]] = {}
        for asset_id, row in image_by_asset.items():
            src_path = old_images_dir / row["filename"]
            if not src_path.exists():
                legacy_rel = Path(str(row["file_path"]).replace("\\", "/"))
                fallback = WORKSPACE_ROOT / legacy_rel
                if fallback.exists():
                    src_path = fallback
            if not src_path.exists():
                continue
            dst_path = TARGET_ASSETS_DIR / row["filename"]
            shutil.copy2(src_path, dst_path)
            copied_assets.add(asset_id)
            relative_file_path = str(Path("09-项目工程/physics-vault/data/assets/questions") / row["filename"]).replace("\\", "/")
            copied_asset_meta[asset_id] = (relative_file_path, dst_path.stat().st_size)

        for row in questions:
            qid = row["question_id"]
            q_assets = [asset for asset in sorted(assets_by_question.get(qid, []), key=lambda item: item["sort_order"]) if asset["asset_id"] in copied_assets]
            filenames = [image_by_asset[a["asset_id"]]["filename"] for a in q_assets]
            figures = [
                {
                    "fig_uuid": asset["placeholder_key"] or asset["asset_id"],
                    "local_path": str(Path("09-项目工程/physics-vault/data/assets/questions") / image_by_asset[asset["asset_id"]]["filename"]).replace("\\", "/"),
                }
                for asset in q_assets
            ]
            source_text = row["source_text"] or (row["paper_id"] or row["primary_paper_id"] or "")

            target_conn.execute(
                """
                INSERT INTO questions (
                    question_id, canonical_title, vault_markdown_path, module, topic2, topic3,
                    difficulty, question_type, status, review_status, review_comment, has_media,
                    primary_paper_id, primary_question_no, import_batch_id, source, content_hash,
                    schema_version, is_mistake, mistake_marked_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qid,
                    row["canonical_title"],
                    row["vault_markdown_path"] or row["markdown_path"],
                    row["module"],
                    row["topic2"],
                    row["topic3"],
                    int(row["difficulty"]) if row["difficulty"] not in (None, "") else 0,
                    row["question_type"],
                    row["status"],
                    review_status_from_status(row["status"]),
                    None,
                    int(row["has_media"] or 0),
                    row["primary_paper_id"],
                    row["primary_question_no"],
                    IMPORT_BATCH_ID,
                    source_text,
                    row["content_hash"],
                    row["schema_version"] or "v1",
                    int(row["is_mistake"] or 0),
                    row["mistake_marked_at"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )

            target_conn.execute(
                """
                INSERT INTO question_text_index (
                    question_id, paper_id, source_id, question_no, markdown_path, title_text,
                    stem_text, stem_clean_text, answer_text, analysis_text, tips_text,
                    options_json, sub_questions_json, figures_json, image_asset_ids_json,
                    image_filenames_json, image_count, tags_json, source_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qid,
                    row["paper_id"] or row["primary_paper_id"],
                    row["source_id"],
                    row["question_no"] or row["primary_question_no"],
                    row["markdown_path"] or row["vault_markdown_path"] or "",
                    row["canonical_title"],
                    row["stem_text"] or "",
                    row["stem_clean_text"],
                    row["answer_text"],
                    row["analysis_text"],
                    row["tips_text"],
                    row["options_json"] or "[]",
                    "[]",
                    json_text(figures),
                    json_text([asset["asset_id"] for asset in q_assets]),
                    json_text(filenames),
                    len(filenames),
                    row["tags_json"] or "[]",
                    source_text,
                    row["created_at"],
                    row["updated_at"],
                ),
            )

        for asset_id, row in image_by_asset.items():
            if asset_id not in copied_assets:
                continue
            relative_file_path, file_size = copied_asset_meta[asset_id]
            mime_type = row["mime_type"] or mimetypes.guess_type(row["filename"])[0] or "image/png"
            target_conn.execute(
                """
                INSERT INTO image_assets (
                    asset_id, filename, file_path, paper_id, question_id, source_id,
                    mime_type, width, height, file_size, sha256, description, extracted_text,
                    image_type, binding_confidence, verified, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    filename = excluded.filename,
                    file_path = excluded.file_path,
                    paper_id = excluded.paper_id,
                    question_id = excluded.question_id,
                    source_id = excluded.source_id,
                    mime_type = excluded.mime_type,
                    width = excluded.width,
                    height = excluded.height,
                    file_size = excluded.file_size,
                    sha256 = excluded.sha256,
                    description = excluded.description,
                    extracted_text = excluded.extracted_text,
                    image_type = excluded.image_type,
                    binding_confidence = excluded.binding_confidence,
                    verified = excluded.verified,
                    updated_at = excluded.updated_at
                """,
                (
                    row["asset_id"], row["filename"], relative_file_path, row["paper_id"], row["question_id"], row["source_id"],
                    mime_type, row["width"], row["height"], file_size, row["sha256"], row["description"],
                    row["extracted_text"], row["image_type"], row["binding_confidence"], row["verified"],
                    row["created_at"], row["updated_at"],
                ),
            )

        for row in question_sources:
            target_conn.execute(
                """
                INSERT INTO question_sources (
                    source_id, question_id, paper_id, question_no, source_role, source_label,
                    page_start, page_end, is_verified, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    question_id = excluded.question_id,
                    paper_id = excluded.paper_id,
                    question_no = excluded.question_no,
                    source_role = excluded.source_role,
                    source_label = excluded.source_label,
                    page_start = excluded.page_start,
                    page_end = excluded.page_end,
                    is_verified = excluded.is_verified,
                    updated_at = excluded.updated_at
                """,
                (
                    row["source_id"], row["question_id"], row["paper_id"], row["question_no"], row["source_role"],
                    row["source_label"], row["page_start"], row["page_end"], row["is_verified"],
                    row["created_at"], row["updated_at"],
                ),
            )

        for row in kp_links:
            link_id = f"{row['question_id']}::{row['rank']}::{row['topic3_id']}"
            target_conn.execute(
                """
                INSERT INTO question_knowledge_points (
                    link_id, question_id, topic3_id, rank, source, confidence, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(question_id, topic3_id) DO UPDATE SET
                    rank = excluded.rank,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    link_id, row["question_id"], row["topic3_id"], row["rank"], row["source"],
                    row["confidence"], row["note"], row["created_at"], row["updated_at"],
                ),
            )

        for row in question_assets:
            if row["asset_id"] not in copied_assets:
                continue
            target_conn.execute(
                """
                INSERT INTO question_assets (
                    link_id, question_id, asset_id, role, sort_order, placeholder_key,
                    is_primary, is_verified, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(link_id) DO UPDATE SET
                    question_id = excluded.question_id,
                    asset_id = excluded.asset_id,
                    role = excluded.role,
                    sort_order = excluded.sort_order,
                    placeholder_key = excluded.placeholder_key,
                    is_primary = excluded.is_primary,
                    is_verified = excluded.is_verified,
                    updated_at = excluded.updated_at
                """,
                (
                    row["link_id"], row["question_id"], row["asset_id"], row["role"], row["sort_order"],
                    row["placeholder_key"], row["is_primary"], row["is_verified"], row["created_at"], row["updated_at"],
                ),
            )

        target_conn.execute(
            """
            INSERT INTO favorite_groups (id, name, sort_order, created_at, updated_at)
            VALUES ('FAV-LEGACY-001', '旧库精选样例', 1, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, sort_order = excluded.sort_order, updated_at = excluded.updated_at
            """
        )
        target_conn.execute(
            """
            INSERT INTO favorite_groups (id, name, sort_order, created_at, updated_at)
            VALUES ('FAV-LEGACY-002', '带图题样例', 2, datetime('now'), datetime('now'))
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, sort_order = excluded.sort_order, updated_at = excluded.updated_at
            """
        )
        for index, qid in enumerate(SAMPLE_QUESTION_IDS[:6]):
            group_id = "FAV-LEGACY-002" if index < 4 else "FAV-LEGACY-001"
            star = 5 if index < 3 else 4
            target_conn.execute(
                """
                INSERT INTO favorite_items (question_id, group_id, star_rating, added_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(question_id) DO UPDATE SET
                    group_id = excluded.group_id,
                    star_rating = excluded.star_rating
                """,
                (qid, group_id, star),
            )

        target_conn.commit()

    # Post-import: fix any encoding issues from legacy data
    from fix_legacy_encoding import fix_database
    enc_stats = fix_database(TARGET_DB, dry_run=False)
    if enc_stats["fixed"] > 0:
        print(f"encoding_fixes={enc_stats['fixed']}")

    print(f"loaded_questions={len(questions)}")
    print(f"loaded_papers={len(papers)}")
    print(f"loaded_knowledge_points={len(knowledge_points)}")
    print(f"copied_assets={len(copied_assets)}")
    print(f"target_db={TARGET_DB}")
    print(f"target_assets={TARGET_ASSETS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
