"""Seed a few demo records into the local SQLite database.

This script is intentionally idempotent:
- papers / questions / sources / knowledge points are upserted
- favorite groups / favorite items are created if missing
- repeated runs keep the same demo rows stable

Usage:
    python scripts/maintenance/seed_demo_data.py
    python scripts/maintenance/seed_demo_data.py --db-path "C:/.../physics_vault.sqlite3"
    python scripts/maintenance/seed_demo_data.py --reset
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = WORKSPACE_ROOT / "02-数据库" / "01-db" / "physics_vault.sqlite3"

DEMO_PAPER_ID = "DEMO-PHY-2026-001"

DEMO_PAPERS: list[dict[str, Any]] = [
    {
        "paper_id": DEMO_PAPER_ID,
        "year": 2026,
        "exam_type": "GK",
        "region": "DEMO",
        "paper_name": "物理题库样例卷（演示数据）",
        "subject": "PHY",
        "source_path": "scripts/maintenance/seed_demo_data.py",
        "source_format": "seed",
        "status": "structured",
        "notes": "用于本地调试的演示数据，不代表真实试卷。",
    }
]

DEMO_KNOWLEDGE_POINTS: list[dict[str, Any]] = [
    {
        "topic1_id": "T1-DEMO-MEC",
        "topic1_name": "力学",
        "topic2_id": "T2-DEMO-KIN",
        "topic2_name": "匀变速直线运动",
        "topic3_id": "T3-DEMO-VT",
        "topic3_name": "速度-时间图像",
        "source_chapter": "样例章节 1",
    },
    {
        "topic1_id": "T1-DEMO-ENE",
        "topic1_name": "力学",
        "topic2_id": "T2-DEMO-ENE",
        "topic2_name": "机械能",
        "topic3_id": "T3-DEMO-ENE",
        "topic3_name": "功能关系与能量守恒",
        "source_chapter": "样例章节 2",
    },
    {
        "topic1_id": "T1-DEMO-ELC",
        "topic1_name": "电学",
        "topic2_id": "T2-DEMO-EF",
        "topic2_name": "电场",
        "topic3_id": "T3-DEMO-EF",
        "topic3_name": "电场强度与叠加",
        "source_chapter": "样例章节 3",
    },
    {
        "topic1_id": "T1-DEMO-OPT",
        "topic1_name": "光学",
        "topic2_id": "T2-DEMO-REF",
        "topic2_name": "几何光学",
        "topic3_id": "T3-DEMO-REF",
        "topic3_name": "折射定律",
        "source_chapter": "样例章节 4",
    },
]

DEMO_QUESTIONS: list[dict[str, Any]] = [
    {
        "question_id": "DEMO-Q-0001",
        "paper_id": DEMO_PAPER_ID,
        "question_no": 1,
        "question_type": "single_choice",
        "canonical_title": "样例题 1",
        "module": "力学",
        "topic2": "匀变速直线运动",
        "topic3": "速度-时间图像",
        "difficulty": "2",
        "status": "已审核",
        "has_media": 0,
        "primary_question_no": 1,
        "vault_markdown_path": "01-Obsidian/02-题库/DEMO-Q-0001.md",
        "stem_text": "一质点做匀加速直线运动，其 $v-t$ 图像如题图所示。下列说法正确的是（ ）",
        "stem_clean_text": "一质点做匀加速直线运动，其 v-t 图像如题图所示。下列说法正确的是（ ）",
        "options_json": [
            {"label": "A", "text": "加速度为零"},
            {"label": "B", "text": "速度随时间均匀增大"},
            {"label": "C", "text": "位移与时间成正比"},
            {"label": "D", "text": "速度始终不变"},
        ],
        "answer_text": "B",
        "analysis_text": "匀加速直线运动中，速度随时间均匀增大，故选 B。",
        "image_asset_ids_json": [],
        "image_filenames_json": [],
        "image_count": 0,
    },
    {
        "question_id": "DEMO-Q-0002",
        "paper_id": DEMO_PAPER_ID,
        "question_no": 2,
        "question_type": "calculation",
        "canonical_title": "样例题 2",
        "module": "力学",
        "topic2": "机械能",
        "topic3": "功能关系与能量守恒",
        "difficulty": "3",
        "status": "已审核",
        "has_media": 0,
        "primary_question_no": 2,
        "vault_markdown_path": "01-Obsidian/02-题库/DEMO-Q-0002.md",
        "stem_text": "质量为 $m$ 的物体在光滑水平面上受恒力作用，若初速度为 0，求 $t$ 时刻的速度表达式。",
        "stem_clean_text": "质量为 m 的物体在光滑水平面上受恒力作用，若初速度为 0，求 t 时刻的速度表达式。",
        "options_json": [],
        "answer_text": "$v=\\frac{F}{m}t$",
        "analysis_text": "由牛顿第二定律 $F=ma$，得 $a=F/m$，再由 $v=at$ 得 $v=\\frac{F}{m}t$。",
        "image_asset_ids_json": [],
        "image_filenames_json": [],
        "image_count": 0,
    },
    {
        "question_id": "DEMO-Q-0003",
        "paper_id": DEMO_PAPER_ID,
        "question_no": 3,
        "question_type": "fill",
        "canonical_title": "样例题 3",
        "module": "电学",
        "topic2": "电场",
        "topic3": "电场强度与叠加",
        "difficulty": "4",
        "status": "待校对",
        "has_media": 0,
        "primary_question_no": 3,
        "vault_markdown_path": "01-Obsidian/02-题库/DEMO-Q-0003.md",
        "stem_text": "在真空中，点电荷的电场强度公式为 $E=$ ________。",
        "stem_clean_text": "在真空中，点电荷的电场强度公式为 E= ________。",
        "options_json": [],
        "answer_text": "$k\\dfrac{Q}{r^2}$",
        "analysis_text": "点电荷在真空中产生的电场强度满足 $E=kQ/r^2$。",
        "image_asset_ids_json": [],
        "image_filenames_json": [],
        "image_count": 0,
    },
    {
        "question_id": "DEMO-Q-0004",
        "paper_id": DEMO_PAPER_ID,
        "question_no": 4,
        "question_type": "experiment",
        "canonical_title": "样例题 4",
        "module": "光学",
        "topic2": "几何光学",
        "topic3": "折射定律",
        "difficulty": "3",
        "status": "已审核",
        "has_media": 0,
        "primary_question_no": 4,
        "vault_markdown_path": "01-Obsidian/02-题库/DEMO-Q-0004.md",
        "stem_text": "某同学用光具座测量凸透镜焦距，简述实验中调节光屏位置的依据。",
        "stem_clean_text": "某同学用光具座测量凸透镜焦距，简述实验中调节光屏位置的依据。",
        "options_json": [],
        "answer_text": "当光屏上出现最清晰的像时，对应成像位置即为合适位置。",
        "analysis_text": "实验中应调节光屏直到像最清晰，此时记录像距并完成焦距测量。",
        "image_asset_ids_json": [],
        "image_filenames_json": [],
        "image_count": 0,
    },
]

DEMO_SOURCES: list[dict[str, Any]] = [
    {
        "question_id": q["question_id"],
        "paper_id": q["paper_id"],
        "question_no": q["question_no"],
        "source_role": "primary",
        "source_label": "演示数据",
        "page_start": q["question_no"],
        "page_end": q["question_no"],
        "is_verified": 1,
    }
    for q in DEMO_QUESTIONS
]

DEMO_KP_LINKS: list[dict[str, Any]] = [
    {
        "question_id": "DEMO-Q-0001",
        "rank": 1,
        "topic3_id": "T3-DEMO-VT",
        "source": "seed",
        "confidence": 1.0,
        "note": "样例题 1",
    },
    {
        "question_id": "DEMO-Q-0002",
        "rank": 1,
        "topic3_id": "T3-DEMO-ENE",
        "source": "seed",
        "confidence": 1.0,
        "note": "样例题 2",
    },
    {
        "question_id": "DEMO-Q-0003",
        "rank": 1,
        "topic3_id": "T3-DEMO-EF",
        "source": "seed",
        "confidence": 1.0,
        "note": "样例题 3",
    },
    {
        "question_id": "DEMO-Q-0004",
        "rank": 1,
        "topic3_id": "T3-DEMO-REF",
        "source": "seed",
        "confidence": 1.0,
        "note": "样例题 4",
    },
]

DEMO_FAVORITE_GROUPS = [
    {"id": "FAV-DEMO-001", "name": "一轮复习", "sort_order": 1},
    {"id": "FAV-DEMO-002", "name": "实验专题", "sort_order": 2},
]

DEMO_FAVORITE_ITEMS = [
    {"question_id": "DEMO-Q-0001", "group_id": "FAV-DEMO-001", "star_rating": 5},
    {"question_id": "DEMO-Q-0002", "group_id": "FAV-DEMO-001", "star_rating": 4},
    {"question_id": "DEMO-Q-0004", "group_id": "FAV-DEMO-002", "star_rating": 3},
]


def resolve_db_path(raw: str | None) -> Path:
    env_path = os.getenv("PHYSICS_VAULT_DB_PATH")
    value = raw or env_path or str(DEFAULT_DB_PATH)
    return Path(value)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS favorite_groups (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS favorite_items (
            question_id TEXT NOT NULL,
            group_id    TEXT,
            star_rating INTEGER NOT NULL DEFAULT 0 CHECK(star_rating >= 0 AND star_rating <= 5),
            added_at    TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (question_id),
            FOREIGN KEY (group_id) REFERENCES favorite_groups(id) ON DELETE SET NULL
        )
        """
    )


def ensure_question_columns(conn: sqlite3.Connection) -> None:
    # The current database may not yet have the mistake flag; add it if needed.
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(questions)").fetchall()
    }
    if "is_mistake" not in columns:
        conn.execute(
            "ALTER TABLE questions ADD COLUMN is_mistake INTEGER NOT NULL DEFAULT 0"
        )
    if "mistake_marked_at" not in columns:
        conn.execute(
            "ALTER TABLE questions ADD COLUMN mistake_marked_at TEXT"
        )


def upsert_papers(conn: sqlite3.Connection) -> None:
    for paper in DEMO_PAPERS:
        conn.execute(
            """
            INSERT INTO papers (
                paper_id, year, exam_type, region, paper_name, subject,
                source_path, source_format, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                paper["paper_id"],
                paper["year"],
                paper["exam_type"],
                paper["region"],
                paper["paper_name"],
                paper["subject"],
                paper["source_path"],
                paper["source_format"],
                paper["status"],
                paper["notes"],
            ),
        )


def upsert_knowledge_points(conn: sqlite3.Connection) -> None:
    for kp in DEMO_KNOWLEDGE_POINTS:
        conn.execute(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name,
                topic2_id, topic2_name,
                topic1_id, topic1_name,
                source_chapter, status, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            ON CONFLICT(topic1_id, topic2_name, topic3_name) DO UPDATE SET
                topic3_id = excluded.topic3_id,
                topic3_name = excluded.topic3_name,
                topic2_id = excluded.topic2_id,
                topic2_name = excluded.topic2_name,
                topic1_name = excluded.topic1_name,
                source_chapter = excluded.source_chapter,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                kp["topic3_id"],
                kp["topic3_name"],
                kp["topic2_id"],
                kp["topic2_name"],
                kp["topic1_id"],
                kp["topic1_name"],
                kp["source_chapter"],
                "演示数据",
            ),
        )


def upsert_questions(conn: sqlite3.Connection) -> None:
    for q in DEMO_QUESTIONS:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, vault_markdown_path,
                module, topic2, topic3, difficulty, question_type,
                status, has_media, primary_paper_id, primary_question_no,
                content_hash, schema_version, created_at, updated_at, is_mistake, mistake_marked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, NULL)
            ON CONFLICT(question_id) DO UPDATE SET
                canonical_title = excluded.canonical_title,
                vault_markdown_path = excluded.vault_markdown_path,
                module = excluded.module,
                topic2 = excluded.topic2,
                topic3 = excluded.topic3,
                difficulty = excluded.difficulty,
                question_type = excluded.question_type,
                status = excluded.status,
                has_media = excluded.has_media,
                primary_paper_id = excluded.primary_paper_id,
                primary_question_no = excluded.primary_question_no,
                content_hash = excluded.content_hash,
                schema_version = excluded.schema_version,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                q["question_id"],
                q["canonical_title"],
                q["vault_markdown_path"],
                q["module"],
                q["topic2"],
                q["topic3"],
                q["difficulty"],
                q["question_type"],
                q["status"],
                q["has_media"],
                q["paper_id"],
                q["primary_question_no"],
                None,
                "v2",
            ),
        )


def upsert_question_text_index(conn: sqlite3.Connection) -> None:
    for q in DEMO_QUESTIONS:
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, paper_id, source_id, question_no,
                markdown_path, stem_text, image_asset_ids_json,
                image_filenames_json, image_count, answer_text,
                analysis_text, tips_text, options_json, stem_clean_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                paper_id = excluded.paper_id,
                source_id = excluded.source_id,
                question_no = excluded.question_no,
                markdown_path = excluded.markdown_path,
                stem_text = excluded.stem_text,
                image_asset_ids_json = excluded.image_asset_ids_json,
                image_filenames_json = excluded.image_filenames_json,
                image_count = excluded.image_count,
                answer_text = excluded.answer_text,
                analysis_text = excluded.analysis_text,
                tips_text = excluded.tips_text,
                options_json = excluded.options_json,
                stem_clean_text = excluded.stem_clean_text,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                q["question_id"],
                q["paper_id"],
                None,
                q["question_no"],
                q["vault_markdown_path"],
                q["stem_text"],
                json_text(q["image_asset_ids_json"]),
                json_text(q["image_filenames_json"]),
                q["image_count"],
                q["answer_text"],
                q["analysis_text"],
                None,
                json_text(q["options_json"]),
                q["stem_clean_text"],
            ),
        )


def upsert_question_sources(conn: sqlite3.Connection) -> None:
    for source in DEMO_SOURCES:
        conn.execute(
            """
            INSERT INTO question_sources (
                source_id, question_id, paper_id, question_no,
                source_role, source_label, page_start, page_end, is_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id, question_no, question_id) DO UPDATE SET
                source_role = excluded.source_role,
                source_label = excluded.source_label,
                page_start = excluded.page_start,
                page_end = excluded.page_end,
                is_verified = excluded.is_verified,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                f"SRC-{source['question_id']}",
                source["question_id"],
                source["paper_id"],
                source["question_no"],
                source["source_role"],
                source["source_label"],
                source["page_start"],
                source["page_end"],
                source["is_verified"],
            ),
        )


def upsert_question_kps(conn: sqlite3.Connection) -> None:
    for link in DEMO_KP_LINKS:
        conn.execute(
            """
            INSERT INTO question_knowledge_points (
                question_id, rank, topic3_id, source, confidence, note
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id, rank) DO UPDATE SET
                topic3_id = excluded.topic3_id,
                source = excluded.source,
                confidence = excluded.confidence,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                link["question_id"],
                link["rank"],
                link["topic3_id"],
                link["source"],
                link["confidence"],
                link["note"],
            ),
        )


def upsert_favorites(conn: sqlite3.Connection) -> None:
    for group in DEMO_FAVORITE_GROUPS:
        conn.execute(
            """
            INSERT INTO favorite_groups (id, name, sort_order)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
            """,
            (group["id"], group["name"], group["sort_order"]),
        )

    for item in DEMO_FAVORITE_ITEMS:
        conn.execute(
            """
            INSERT INTO favorite_items (question_id, group_id, star_rating)
            VALUES (?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                group_id = excluded.group_id,
                star_rating = excluded.star_rating
            """,
            (item["question_id"], item["group_id"], item["star_rating"]),
        )


def reset_demo_rows(conn: sqlite3.Connection) -> None:
    question_ids = [q["question_id"] for q in DEMO_QUESTIONS]
    placeholders = ",".join("?" for _ in question_ids)

    conn.execute(
        f"DELETE FROM favorite_items WHERE question_id IN ({placeholders})",
        question_ids,
    )
    conn.execute(
        f"DELETE FROM question_knowledge_points WHERE question_id IN ({placeholders})",
        question_ids,
    )
    conn.execute(
        f"DELETE FROM question_sources WHERE question_id IN ({placeholders})",
        question_ids,
    )
    conn.execute(
        f"DELETE FROM question_text_index WHERE question_id IN ({placeholders})",
        question_ids,
    )
    conn.execute(
        f"DELETE FROM questions WHERE question_id IN ({placeholders})",
        question_ids,
    )
    conn.execute(
        f"DELETE FROM papers WHERE paper_id IN (?)",
        (DEMO_PAPER_ID,),
    )
    conn.execute("DELETE FROM favorite_groups WHERE id IN (?, ?)", ("FAV-DEMO-001", "FAV-DEMO-002"))


def seed(db_path: Path, reset: bool = False) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema(conn)
        ensure_question_columns(conn)

        if reset:
            reset_demo_rows(conn)

        upsert_papers(conn)
        upsert_knowledge_points(conn)
        upsert_questions(conn)
        upsert_question_text_index(conn)
        upsert_question_sources(conn)
        upsert_question_kps(conn)
        upsert_favorites(conn)

        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo records into the physics vault SQLite database.")
    parser.add_argument("--db-path", dest="db_path", help="Explicit path to physics_vault.sqlite3")
    parser.add_argument("--reset", action="store_true", help="Remove the demo rows first, then seed them again.")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db_path)
    seed(db_path, reset=args.reset)
    print(f"Seeded demo data into: {db_path}")
    print(f"Paper: {DEMO_PAPER_ID}")
    print("Questions:", ", ".join(q["question_id"] for q in DEMO_QUESTIONS))


if __name__ == "__main__":
    main()
