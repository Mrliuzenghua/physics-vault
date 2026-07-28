from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_SRC = PROJECT_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from physics_vault_api.database import connect_db  # noqa: E402
from physics_vault_api.db_schema import initialize_database, reset_database  # noqa: E402
from physics_vault_api.paths import default_db_path  # noqa: E402


BATCH_ID = "BATCH-STANDARD-DEMO-2026"


PAPERS: list[dict[str, Any]] = [
    {
        "paper_id": "PAPER-DEMO-MECH-2026",
        "year": 2026,
        "exam_type": "demo",
        "region": "standard",
        "paper_name": "标准样例卷 A：力学基础",
        "source_path": "scripts/maintenance/seed_standard_dataset.py",
        "source_format": "seed",
        "notes": "标准化演示数据，覆盖运动学、动力学、能量和动量。",
    },
    {
        "paper_id": "PAPER-DEMO-EM-2026",
        "year": 2026,
        "exam_type": "demo",
        "region": "standard",
        "paper_name": "标准样例卷 B：电磁学基础",
        "source_path": "scripts/maintenance/seed_standard_dataset.py",
        "source_format": "seed",
        "notes": "标准化演示数据，覆盖电场、电路、磁场和电磁感应。",
    },
    {
        "paper_id": "PAPER-DEMO-MODERN-2026",
        "year": 2026,
        "exam_type": "demo",
        "region": "standard",
        "paper_name": "标准样例卷 C：光学与热学",
        "source_path": "scripts/maintenance/seed_standard_dataset.py",
        "source_format": "seed",
        "notes": "标准化演示数据，覆盖光学、热学、振动与波。",
    },
]


KNOWLEDGE_POINTS: list[dict[str, Any]] = [
    {
        "topic1_id": "KP-MECH",
        "topic1_name": "力学",
        "topic2_id": "KP-MECH-KIN",
        "topic2_name": "运动学",
        "topic3_id": "KP-MECH-KIN-VT",
        "topic3_name": "匀变速直线运动",
        "source_chapter": "必修一 第一章",
    },
    {
        "topic1_id": "KP-MECH",
        "topic1_name": "力学",
        "topic2_id": "KP-MECH-DYN",
        "topic2_name": "相互作用与牛顿运动定律",
        "topic3_id": "KP-MECH-DYN-NEWTON2",
        "topic3_name": "牛顿第二定律",
        "source_chapter": "必修一 第三章",
    },
    {
        "topic1_id": "KP-MECH",
        "topic1_name": "力学",
        "topic2_id": "KP-MECH-ENERGY",
        "topic2_name": "机械能",
        "topic3_id": "KP-MECH-ENERGY-CONSERVATION",
        "topic3_name": "机械能守恒",
        "source_chapter": "必修二 第七章",
    },
    {
        "topic1_id": "KP-MECH",
        "topic1_name": "力学",
        "topic2_id": "KP-MECH-MOMENTUM",
        "topic2_name": "动量",
        "topic3_id": "KP-MECH-MOMENTUM-CONSERVATION",
        "topic3_name": "动量守恒",
        "source_chapter": "选择性必修一 第一章",
    },
    {
        "topic1_id": "KP-EM",
        "topic1_name": "电磁学",
        "topic2_id": "KP-EM-EFIELD",
        "topic2_name": "静电场",
        "topic3_id": "KP-EM-EFIELD-STRENGTH",
        "topic3_name": "电场强度",
        "source_chapter": "选择性必修二 第一章",
    },
    {
        "topic1_id": "KP-EM",
        "topic1_name": "电磁学",
        "topic2_id": "KP-EM-CIRCUIT",
        "topic2_name": "恒定电流",
        "topic3_id": "KP-EM-CIRCUIT-OHM",
        "topic3_name": "闭合电路欧姆定律",
        "source_chapter": "选择性必修二 第二章",
    },
    {
        "topic1_id": "KP-EM",
        "topic1_name": "电磁学",
        "topic2_id": "KP-EM-MAGNETIC",
        "topic2_name": "磁场",
        "topic3_id": "KP-EM-MAGNETIC-LORENTZ",
        "topic3_name": "洛伦兹力",
        "source_chapter": "选择性必修二 第三章",
    },
    {
        "topic1_id": "KP-EM",
        "topic1_name": "电磁学",
        "topic2_id": "KP-EM-INDUCTION",
        "topic2_name": "电磁感应",
        "topic3_id": "KP-EM-INDUCTION-FARADAY",
        "topic3_name": "法拉第电磁感应定律",
        "source_chapter": "选择性必修二 第四章",
    },
    {
        "topic1_id": "KP-OPTICS",
        "topic1_name": "光学",
        "topic2_id": "KP-OPTICS-GEOMETRY",
        "topic2_name": "几何光学",
        "topic3_id": "KP-OPTICS-GEOMETRY-REFRACTION",
        "topic3_name": "折射定律",
        "source_chapter": "选择性必修一 第四章",
    },
    {
        "topic1_id": "KP-THERMO",
        "topic1_name": "热学",
        "topic2_id": "KP-THERMO-GAS",
        "topic2_name": "气体实验定律",
        "topic3_id": "KP-THERMO-GAS-BOYLE",
        "topic3_name": "玻意耳定律",
        "source_chapter": "选择性必修三 第二章",
    },
    {
        "topic1_id": "KP-WAVE",
        "topic1_name": "振动与波",
        "topic2_id": "KP-WAVE-MECHANICAL",
        "topic2_name": "机械波",
        "topic3_id": "KP-WAVE-MECHANICAL-IMAGE",
        "topic3_name": "波形图与振动图像",
        "source_chapter": "选择性必修一 第三章",
    },
    {
        "topic1_id": "KP-MODERN",
        "topic1_name": "近代物理",
        "topic2_id": "KP-MODERN-ATOM",
        "topic2_name": "原子物理",
        "topic3_id": "KP-MODERN-ATOM-PHOTOELECTRIC",
        "topic3_name": "光电效应",
        "source_chapter": "选择性必修三 第四章",
    },
]


QUESTIONS: list[dict[str, Any]] = [
    {
        "question_id": "Q-DEMO-2026-001",
        "paper_id": "PAPER-DEMO-MECH-2026",
        "question_no": 1,
        "question_type": "single_choice",
        "difficulty": 2,
        "topic3_id": "KP-MECH-KIN-VT",
        "status": "已审核",
        "title": "匀变速直线运动速度公式",
        "stem": "一辆小车从静止开始做匀加速直线运动，加速度为 2 m/s^2。小车在 3 s 末的速度大小为（    ）",
        "options": [
            {"label": "A", "text": "2 m/s"},
            {"label": "B", "text": "3 m/s"},
            {"label": "C", "text": "5 m/s"},
            {"label": "D", "text": "6 m/s"},
        ],
        "answer": "D",
        "analysis": "由速度公式 v = v0 + at，且 v0 = 0、a = 2 m/s^2、t = 3 s，得 v = 6 m/s。",
    },
    {
        "question_id": "Q-DEMO-2026-002",
        "paper_id": "PAPER-DEMO-MECH-2026",
        "question_no": 2,
        "question_type": "calculation",
        "difficulty": 3,
        "topic3_id": "KP-MECH-DYN-NEWTON2",
        "status": "已审核",
        "title": "牛顿第二定律计算加速度",
        "stem": "质量为 4 kg 的物体放在光滑水平面上，受到 12 N 的水平恒力作用。求物体的加速度。",
        "options": [],
        "answer": "3 m/s^2",
        "analysis": "由牛顿第二定律 F = ma，得 a = F/m = 12/4 = 3 m/s^2。",
    },
    {
        "question_id": "Q-DEMO-2026-003",
        "paper_id": "PAPER-DEMO-MECH-2026",
        "question_no": 3,
        "question_type": "single_choice",
        "difficulty": 3,
        "topic3_id": "KP-MECH-ENERGY-CONSERVATION",
        "status": "已审核",
        "title": "机械能守恒判断",
        "stem": "不计空气阻力，小球从某一高度自由下落。下列说法正确的是（    ）",
        "options": [
            {"label": "A", "text": "重力势能增加，动能减少"},
            {"label": "B", "text": "机械能保持不变"},
            {"label": "C", "text": "机械能不断减少"},
            {"label": "D", "text": "动能保持不变"},
        ],
        "answer": "B",
        "analysis": "只有重力做功时，小球的重力势能和动能相互转化，机械能守恒。",
    },
    {
        "question_id": "Q-DEMO-2026-004",
        "paper_id": "PAPER-DEMO-MECH-2026",
        "question_no": 4,
        "question_type": "calculation",
        "difficulty": 4,
        "topic3_id": "KP-MECH-MOMENTUM-CONSERVATION",
        "status": "待校对",
        "title": "完全非弹性碰撞速度",
        "stem": "质量分别为 1 kg 和 2 kg 的两小车在光滑水平轨道上相向运动，速度大小分别为 6 m/s 和 3 m/s，碰后粘在一起。取 1 kg 小车原运动方向为正方向，求碰后共同速度。",
        "options": [],
        "answer": "0 m/s",
        "analysis": "系统动量守恒：p = 1*6 + 2*(-3) = 0，因此碰后共同速度 v = 0。",
    },
    {
        "question_id": "Q-DEMO-2026-005",
        "paper_id": "PAPER-DEMO-EM-2026",
        "question_no": 1,
        "question_type": "fill",
        "difficulty": 3,
        "topic3_id": "KP-EM-EFIELD-STRENGTH",
        "status": "已审核",
        "title": "点电荷电场强度",
        "stem": "真空中点电荷 Q 在距其 r 处产生的电场强度大小 E = ______。",
        "options": [],
        "answer": "kQ/r^2",
        "analysis": "点电荷电场强度公式为 E = kQ/r^2，方向沿径向，由电荷正负决定。",
    },
    {
        "question_id": "Q-DEMO-2026-006",
        "paper_id": "PAPER-DEMO-EM-2026",
        "question_no": 2,
        "question_type": "calculation",
        "difficulty": 4,
        "topic3_id": "KP-EM-CIRCUIT-OHM",
        "status": "已审核",
        "title": "闭合电路欧姆定律",
        "stem": "电源电动势为 12 V，内阻为 1 Ω，外电阻为 5 Ω。求电路中的电流。",
        "options": [],
        "answer": "2 A",
        "analysis": "闭合电路电流 I = E/(R+r) = 12/(5+1) = 2 A。",
    },
    {
        "question_id": "Q-DEMO-2026-007",
        "paper_id": "PAPER-DEMO-EM-2026",
        "question_no": 3,
        "question_type": "single_choice",
        "difficulty": 3,
        "topic3_id": "KP-EM-MAGNETIC-LORENTZ",
        "status": "已审核",
        "title": "洛伦兹力方向",
        "stem": "正电荷以速度 v 垂直进入匀强磁场。关于洛伦兹力，下列说法正确的是（    ）",
        "options": [
            {"label": "A", "text": "方向一定与速度方向相同"},
            {"label": "B", "text": "方向一定与速度方向相反"},
            {"label": "C", "text": "方向垂直于速度和磁场所决定的平面"},
            {"label": "D", "text": "大小与速度无关"},
        ],
        "answer": "C",
        "analysis": "洛伦兹力方向由左手定则判断，始终垂直于速度方向和磁场方向。",
    },
    {
        "question_id": "Q-DEMO-2026-008",
        "paper_id": "PAPER-DEMO-EM-2026",
        "question_no": 4,
        "question_type": "fill",
        "difficulty": 4,
        "topic3_id": "KP-EM-INDUCTION-FARADAY",
        "status": "待校对",
        "title": "法拉第电磁感应定律",
        "stem": "穿过闭合回路的磁通量变化越快，回路中感应电动势的大小越 ______。",
        "options": [],
        "answer": "大",
        "analysis": "由 E = n|ΔΦ/Δt| 可知，磁通量变化率越大，感应电动势越大。",
    },
    {
        "question_id": "Q-DEMO-2026-009",
        "paper_id": "PAPER-DEMO-MODERN-2026",
        "question_no": 1,
        "question_type": "experiment",
        "difficulty": 3,
        "topic3_id": "KP-OPTICS-GEOMETRY-REFRACTION",
        "status": "已审核",
        "title": "折射定律实验",
        "stem": "某同学用半圆形玻璃砖研究光的折射规律。实验中应如何确定入射角和折射角？",
        "options": [],
        "answer": "分别测量入射光线、折射光线与法线之间的夹角。",
        "analysis": "折射定律中的入射角和折射角均是光线与法线的夹角，而不是与界面的夹角。",
    },
    {
        "question_id": "Q-DEMO-2026-010",
        "paper_id": "PAPER-DEMO-MODERN-2026",
        "question_no": 2,
        "question_type": "calculation",
        "difficulty": 3,
        "topic3_id": "KP-THERMO-GAS-BOYLE",
        "status": "已审核",
        "title": "玻意耳定律计算",
        "stem": "一定质量理想气体温度不变，初态压强为 1.0×10^5 Pa、体积为 4 L。若体积变为 2 L，求末态压强。",
        "options": [],
        "answer": "2.0×10^5 Pa",
        "analysis": "温度不变时 p1V1 = p2V2，故 p2 = p1V1/V2 = 2.0×10^5 Pa。",
    },
    {
        "question_id": "Q-DEMO-2026-011",
        "paper_id": "PAPER-DEMO-MODERN-2026",
        "question_no": 3,
        "question_type": "single_choice",
        "difficulty": 4,
        "topic3_id": "KP-WAVE-MECHANICAL-IMAGE",
        "status": "已审核",
        "title": "机械波波速关系",
        "stem": "一列简谐横波的波长为 2 m，频率为 5 Hz，则该波的传播速度为（    ）",
        "options": [
            {"label": "A", "text": "0.4 m/s"},
            {"label": "B", "text": "2.5 m/s"},
            {"label": "C", "text": "7 m/s"},
            {"label": "D", "text": "10 m/s"},
        ],
        "answer": "D",
        "analysis": "波速 v = λf = 2×5 = 10 m/s。",
    },
    {
        "question_id": "Q-DEMO-2026-012",
        "paper_id": "PAPER-DEMO-MODERN-2026",
        "question_no": 4,
        "question_type": "single_choice",
        "difficulty": 4,
        "topic3_id": "KP-MODERN-ATOM-PHOTOELECTRIC",
        "status": "待校对",
        "title": "光电效应截止频率",
        "stem": "关于光电效应，下列说法正确的是（    ）",
        "options": [
            {"label": "A", "text": "只要光强足够大，任意频率的光都能产生光电效应"},
            {"label": "B", "text": "入射光频率必须大于金属的截止频率"},
            {"label": "C", "text": "光电子最大初动能只与光强有关"},
            {"label": "D", "text": "截止频率与金属材料无关"},
        ],
        "answer": "B",
        "analysis": "发生光电效应要求入射光频率不低于金属的截止频率，最大初动能与频率有关。",
    },
]


COLLECTIONS = [
    {"id": "COL-DEMO-MECH", "name": "标准样例：力学", "parent_id": None, "type": "directory"},
    {"id": "COL-DEMO-EM", "name": "标准样例：电磁学", "parent_id": None, "type": "directory"},
    {"id": "COL-DEMO-MODERN", "name": "标准样例：光学热学", "parent_id": None, "type": "directory"},
]


FAVORITE_GROUPS = [
    {"id": "FAV-DEMO-CORE", "name": "核心例题", "sort_order": 1},
    {"id": "FAV-DEMO-REVIEW", "name": "待复习题", "sort_order": 2},
]


def compact_text(value: str) -> str:
    return " ".join(value.split())


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def content_hash(question: dict[str, Any]) -> str:
    source = "\n".join(
        [
            question["title"],
            question["stem"],
            question["answer"],
            question["analysis"],
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def kp_by_id() -> dict[str, dict[str, Any]]:
    return {item["topic3_id"]: item for item in KNOWLEDGE_POINTS}


def clear_domain_data(conn) -> None:
    tables = [
        "collection_questions",
        "collections",
        "favorite_items",
        "favorite_groups",
        "question_annotations",
        "question_versions",
        "question_assets",
        "image_assets",
        "question_knowledge_points",
        "question_sources",
        "question_text_index",
        "review_queue",
        "embeddings",
        "processing_runs",
        "knowledge_cache",
        "questions",
        "papers",
        "import_batches",
        "knowledge_points",
    ]
    for table in tables:
        conn.execute(f"DELETE FROM {table}")


def seed_import_batch(conn) -> None:
    conn.execute(
        """
        INSERT INTO import_batches (
            import_batch_id, batch_name, source_type, source_path,
            pipeline_mode, status, total_files, total_questions, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            BATCH_ID,
            "标准化演示数据导入",
            "seed",
            "scripts/maintenance/seed_standard_dataset.py",
            "standard_seed",
            "completed",
            len(PAPERS),
            len(QUESTIONS),
            "清理旧样例数据后写入的标准化题库样例。",
        ),
    )


def seed_papers(conn) -> None:
    for paper in PAPERS:
        conn.execute(
            """
            INSERT INTO papers (
                paper_id, year, exam_type, region, paper_name, subject,
                source_path, source_format, status, notes
            ) VALUES (?, ?, ?, ?, ?, 'PHY', ?, ?, 'structured', ?)
            """,
            (
                paper["paper_id"],
                paper["year"],
                paper["exam_type"],
                paper["region"],
                paper["paper_name"],
                paper["source_path"],
                paper["source_format"],
                paper["notes"],
            ),
        )


def seed_knowledge_points(conn) -> None:
    for kp in KNOWLEDGE_POINTS:
        conn.execute(
            """
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name,
                topic1_id, topic1_name, source_chapter, status, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                kp["topic3_id"],
                kp["topic3_name"],
                kp["topic2_id"],
                kp["topic2_name"],
                kp["topic1_id"],
                kp["topic1_name"],
                kp["source_chapter"],
                "标准化样例知识点",
            ),
        )


def seed_questions(conn) -> None:
    knowledge = kp_by_id()
    for question in QUESTIONS:
        kp = knowledge[question["topic3_id"]]
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, vault_markdown_path,
                module, topic2, topic3, difficulty, question_type,
                status, review_status, has_media, primary_paper_id,
                primary_question_no, import_batch_id, origin_file,
                origin_page, source, content_hash, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 'v2')
            """,
            (
                question["question_id"],
                question["title"],
                f"standard-demo/{question['question_id']}.md",
                kp["topic1_name"],
                kp["topic2_name"],
                kp["topic3_name"],
                question["difficulty"],
                question["question_type"],
                question["status"],
                "approved" if question["status"] == "已审核" else "reviewing",
                question["paper_id"],
                question["question_no"],
                BATCH_ID,
                f"{question['paper_id']}.seed",
                question["question_no"],
                "standard_seed",
                content_hash(question),
            ),
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, paper_id, source_id, question_no,
                markdown_path, title_text, stem_text, stem_clean_text,
                answer_text, analysis_text, options_json,
                sub_questions_json, figures_json, image_asset_ids_json,
                image_filenames_json, image_count, tags_json, source_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', '[]', 0, ?, ?)
            """,
            (
                question["question_id"],
                question["paper_id"],
                f"SRC-{question['question_id']}",
                question["question_no"],
                f"standard-demo/{question['question_id']}.md",
                question["title"],
                question["stem"],
                compact_text(question["stem"]),
                question["answer"],
                question["analysis"],
                json_text(question["options"]),
                json_text([kp["topic1_name"], kp["topic2_name"], kp["topic3_name"]]),
                "标准化演示数据",
            ),
        )
        conn.execute(
            """
            INSERT INTO question_sources (
                source_id, question_id, paper_id, question_no,
                source_role, source_label, page_start, page_end, is_verified
            ) VALUES (?, ?, ?, ?, 'primary', ?, ?, ?, 1)
            """,
            (
                f"SRC-{question['question_id']}",
                question["question_id"],
                question["paper_id"],
                question["question_no"],
                "标准样例卷",
                question["question_no"],
                question["question_no"],
            ),
        )
        conn.execute(
            """
            INSERT INTO question_knowledge_points (
                link_id, question_id, topic3_id, rank, source, confidence, note
            ) VALUES (?, ?, ?, 1, 'standard_seed', 1.0, ?)
            """,
            (
                f"QKP-{question['question_id']}",
                question["question_id"],
                question["topic3_id"],
                question["title"],
            ),
        )


def seed_collections(conn) -> None:
    for collection in COLLECTIONS:
        conn.execute(
            """
            INSERT INTO collections (id, name, parent_id, type)
            VALUES (?, ?, ?, ?)
            """,
            (
                collection["id"],
                collection["name"],
                collection["parent_id"],
                collection["type"],
            ),
        )

    collection_by_paper = {
        "PAPER-DEMO-MECH-2026": "COL-DEMO-MECH",
        "PAPER-DEMO-EM-2026": "COL-DEMO-EM",
        "PAPER-DEMO-MODERN-2026": "COL-DEMO-MODERN",
    }
    for question in QUESTIONS:
        conn.execute(
            """
            INSERT INTO collection_questions (collection_id, question_id)
            VALUES (?, ?)
            """,
            (collection_by_paper[question["paper_id"]], question["question_id"]),
        )


def seed_favorites(conn) -> None:
    for group in FAVORITE_GROUPS:
        conn.execute(
            """
            INSERT INTO favorite_groups (id, name, sort_order)
            VALUES (?, ?, ?)
            """,
            (group["id"], group["name"], group["sort_order"]),
        )

    favorites = [
        ("Q-DEMO-2026-001", "FAV-DEMO-CORE", 5),
        ("Q-DEMO-2026-002", "FAV-DEMO-CORE", 5),
        ("Q-DEMO-2026-006", "FAV-DEMO-CORE", 4),
        ("Q-DEMO-2026-004", "FAV-DEMO-REVIEW", 4),
        ("Q-DEMO-2026-008", "FAV-DEMO-REVIEW", 3),
        ("Q-DEMO-2026-012", "FAV-DEMO-REVIEW", 3),
    ]
    for question_id, group_id, star_rating in favorites:
        conn.execute(
            """
            INSERT INTO favorite_items (question_id, group_id, star_rating)
            VALUES (?, ?, ?)
            """,
            (question_id, group_id, star_rating),
        )


def seed_review_queue(conn) -> None:
    for question in QUESTIONS:
        if question["status"] != "待校对":
            continue
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type,
                status, priority, reason, payload_json
            ) VALUES (?, 'question', ?, 'manual', 'pending', ?, ?, ?)
            """,
            (
                f"REV-{question['question_id']}",
                question["question_id"],
                10 - question["difficulty"],
                "标准样例中保留的待校对题，用于演示审核队列。",
                json_text({"source": "standard_seed", "title": question["title"]}),
            ),
        )


def seed_processing_run(conn) -> None:
    conn.execute(
        """
        INSERT INTO processing_runs (
            run_id, pipeline_name, pipeline_version, status,
            started_at, finished_at, operator, summary_json
        ) VALUES (
            'RUN-STANDARD-SEED-2026',
            'standard_dataset_seed',
            '2026.07.28',
            'completed',
            datetime('now'),
            datetime('now'),
            'codex',
            ?
        )
        """,
        (
            json_text(
                {
                    "papers": len(PAPERS),
                    "questions": len(QUESTIONS),
                    "knowledge_points": len(KNOWLEDGE_POINTS),
                }
            ),
        ),
    )


def rebuild_fts(conn) -> None:
    exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'question_search_fts'
        """
    ).fetchone()
    if not exists:
        return
    conn.execute("DELETE FROM question_search_fts")
    conn.execute(
        """
        INSERT INTO question_search_fts(question_id, title, stem, answer, analysis, tags, source)
        SELECT
            q.question_id,
            COALESCE(qti.title_text, q.canonical_title, ''),
            COALESCE(qti.stem_clean_text, qti.stem_text, ''),
            COALESCE(qti.answer_text, ''),
            COALESCE(qti.analysis_text, ''),
            COALESCE(qti.tags_json, ''),
            COALESCE(qti.source_text, q.source, q.primary_paper_id, '')
        FROM questions q
        LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
        """
    )


def seed_standard_dataset(db_path: Path, *, reset: bool, backup: bool) -> tuple[Path, Path | None]:
    backup_path: Path | None = None
    if reset:
        _, backup_path = reset_database(db_path, backup=backup)
    else:
        initialize_database(db_path)

    with connect_db(db_path) as conn:
        clear_domain_data(conn)
        seed_import_batch(conn)
        seed_papers(conn)
        seed_knowledge_points(conn)
        seed_questions(conn)
        seed_collections(conn)
        seed_favorites(conn)
        seed_review_queue(conn)
        seed_processing_run(conn)
        rebuild_fts(conn)
        conn.commit()

    return db_path, backup_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reset old sample data and seed a standardized Physics Vault demo dataset.",
    )
    parser.add_argument(
        "--db-path",
        default=str(default_db_path()),
        help="Target SQLite file path. Defaults to data/app-db/physics_vault.sqlite3.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Keep the current database file, but clear domain data before seeding.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a backup when resetting the database file.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db_path)
    resolved, backup_path = seed_standard_dataset(
        db_path,
        reset=not args.no_reset,
        backup=not args.no_backup,
    )
    print(f"standardized database: {resolved}")
    if backup_path:
        print(f"backup: {backup_path}")
    print(f"papers: {len(PAPERS)}")
    print(f"questions: {len(QUESTIONS)}")
    print(f"knowledge_points: {len(KNOWLEDGE_POINTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
