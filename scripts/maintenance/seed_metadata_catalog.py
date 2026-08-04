"""Seed the standard knowledge tree and tag catalog without touching questions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from physics_vault_api.database import connect_db  # noqa: E402
from physics_vault_api.db_schema import initialize_database  # noqa: E402
from physics_vault_api.paths import default_db_path  # noqa: E402
from physics_vault_api.services.metadata_management import MetadataManagementService  # noqa: E402


HIERARCHY: list[tuple[str, str, str, str, list[tuple[str, str, str]]]] = [
    ("KP-MECH", "力学", "KP-MECH-KIN", "运动学", [
        ("VT", "匀变速直线运动", "必修一"), ("FREEFALL", "自由落体运动", "必修一"),
        ("PROJECTILE", "抛体运动", "必修二"), ("CIRCULAR", "圆周运动", "必修二"),
        ("RELATIVE", "运动的合成与分解", "必修二"),
    ]),
    ("KP-MECH", "力学", "KP-MECH-DYN", "相互作用与牛顿运动定律", [
        ("FORCE", "常见力与受力分析", "必修一"), ("EQUILIBRIUM", "共点力的平衡", "必修一"),
        ("NEWTON2", "牛顿第二定律", "必修一"), ("NEWTON3", "牛顿第三定律", "必修一"),
        ("CONNECTED", "连接体问题", "必修一"), ("WEIGHT", "超重与失重", "必修一"),
    ]),
    ("KP-MECH", "力学", "KP-MECH-GRAVITY", "万有引力与航天", [
        ("LAW", "万有引力定律", "必修二"), ("CELESTIAL", "天体质量与密度", "必修二"),
        ("ORBIT", "卫星轨道", "必修二"), ("COSMIC", "宇宙速度", "必修二"),
    ]),
    ("KP-MECH", "力学", "KP-MECH-ENERGY", "机械能", [
        ("WORK", "功和功率", "必修二"), ("KINETIC", "动能定理", "必修二"),
        ("POTENTIAL", "重力势能与弹性势能", "必修二"),
        ("CONSERVATION", "机械能守恒", "必修二"), ("FUNCTION", "功能关系", "必修二"),
    ]),
    ("KP-MECH", "力学", "KP-MECH-MOMENTUM", "动量", [
        ("IMPULSE", "冲量与动量定理", "选择性必修一"),
        ("CONSERVATION", "动量守恒", "选择性必修一"),
        ("COLLISION", "碰撞", "选择性必修一"), ("RECOIL", "反冲与人船模型", "选择性必修一"),
    ]),
    ("KP-MECH", "力学", "KP-MECH-OSC", "机械振动", [
        ("SHM", "简谐运动", "选择性必修一"), ("PENDULUM", "单摆", "选择性必修一"),
        ("ENERGY", "简谐运动的能量", "选择性必修一"), ("RESONANCE", "受迫振动与共振", "选择性必修一"),
    ]),
    ("KP-EM", "电磁学", "KP-EM-EFIELD", "静电场", [
        ("COULOMB", "库仑定律", "必修三"), ("STRENGTH", "电场强度", "必修三"),
        ("POTENTIAL", "电势能与电势", "必修三"), ("CAPACITOR", "电容器", "必修三"),
        ("PARTICLE", "带电粒子在电场中的运动", "必修三"),
    ]),
    ("KP-EM", "电磁学", "KP-EM-CIRCUIT", "恒定电流", [
        ("CURRENT", "电流与电阻定律", "必修三"), ("OHM", "闭合电路欧姆定律", "必修三"),
        ("POWER", "电功和电功率", "必修三"), ("SERIES", "串并联电路", "必修三"),
        ("METER", "电表改装", "必修三"), ("EXPERIMENT", "测量电阻与电源电动势", "必修三"),
    ]),
    ("KP-EM", "电磁学", "KP-EM-MAGNETIC", "磁场", [
        ("AMPERE", "安培力", "选择性必修二"), ("LORENTZ", "洛伦兹力", "选择性必修二"),
        ("PARTICLE", "带电粒子在磁场中的运动", "选择性必修二"),
        ("COMBINED", "带电粒子在复合场中的运动", "选择性必修二"),
    ]),
    ("KP-EM", "电磁学", "KP-EM-INDUCTION", "电磁感应", [
        ("FLUX", "磁通量", "选择性必修二"), ("FARADAY", "法拉第电磁感应定律", "选择性必修二"),
        ("LENZ", "楞次定律", "选择性必修二"), ("ROD", "导体棒切割磁感线", "选择性必修二"),
        ("CIRCUIT", "电磁感应中的电路与图像", "选择性必修二"),
    ]),
    ("KP-EM", "电磁学", "KP-EM-AC", "交变电流", [
        ("DESCRIPTION", "交变电流的描述", "选择性必修二"), ("EFFECTIVE", "交变电流有效值", "选择性必修二"),
        ("TRANSFORMER", "变压器", "选择性必修二"), ("TRANSMISSION", "远距离输电", "选择性必修二"),
    ]),
    ("KP-EM", "电磁学", "KP-EM-EMOSC", "电磁振荡与电磁波", [
        ("LC", "LC振荡回路", "选择性必修二"), ("WAVE", "电磁波", "选择性必修二"),
    ]),
    ("KP-WAVE", "振动与波", "KP-WAVE-MECHANICAL", "机械波", [
        ("IMAGE", "波形图与振动图像", "选择性必修一"), ("PROPAGATION", "机械波的传播", "选择性必修一"),
        ("SUPERPOSITION", "波的叠加与干涉", "选择性必修一"), ("DOPPLER", "多普勒效应", "选择性必修一"),
    ]),
    ("KP-OPTICS", "光学", "KP-OPTICS-GEOMETRY", "几何光学", [
        ("REFLECTION", "光的反射", "选择性必修一"), ("REFRACTION", "折射定律", "选择性必修一"),
        ("TOTAL", "全反射", "选择性必修一"),
    ]),
    ("KP-OPTICS", "光学", "KP-OPTICS-PHYSICAL", "物理光学", [
        ("INTERFERENCE", "光的干涉", "选择性必修一"), ("DIFFRACTION", "光的衍射", "选择性必修一"),
        ("POLARIZATION", "光的偏振", "选择性必修一"), ("SPECTRUM", "光谱", "选择性必修三"),
    ]),
    ("KP-THERMO", "热学", "KP-THERMO-GAS", "气体实验定律", [
        ("BOYLE", "玻意耳定律", "选择性必修三"), ("CHARLES", "查理定律", "选择性必修三"),
        ("GAYLUSSAC", "盖-吕萨克定律", "选择性必修三"), ("STATE", "理想气体状态方程", "选择性必修三"),
    ]),
    ("KP-THERMO", "热学", "KP-THERMO-LAW", "热力学定律", [
        ("FIRST", "热力学第一定律", "选择性必修三"), ("SECOND", "热力学第二定律", "选择性必修三"),
        ("ENERGY", "能量守恒与能源", "选择性必修三"),
    ]),
    ("KP-THERMO", "热学", "KP-THERMO-MOLECULAR", "分子动理论", [
        ("MOTION", "分子热运动", "选择性必修三"), ("ENERGY", "分子动能与势能", "选择性必修三"),
    ]),
    ("KP-MODERN", "近代物理", "KP-MODERN-ATOM", "原子物理", [
        ("PHOTOELECTRIC", "光电效应", "选择性必修三"), ("WAVE", "光的波粒二象性", "选择性必修三"),
        ("BOHR", "氢原子能级与玻尔模型", "选择性必修三"), ("MATTERWAVE", "物质波", "选择性必修三"),
    ]),
    ("KP-MODERN", "近代物理", "KP-MODERN-NUCLEAR", "原子核物理", [
        ("RADIOACTIVE", "天然放射现象", "选择性必修三"), ("REACTION", "核反应", "选择性必修三"),
        ("ENERGY", "质量亏损与核能", "选择性必修三"), ("FISSION", "裂变与聚变", "选择性必修三"),
    ]),
]

CURRICULUM_STANDARD = "普通高中物理课程标准（2017年版2020年修订）"
TEXTBOOK_EDITION = "人教版普通高中物理教材"


TAG_CATALOG: dict[str, list[str]] = {
    "方法": ["图像法", "比例法", "等效法", "逐差法", "整体法", "隔离法", "极限法", "假设法", "量纲法", "几何关系", "特殊值法"],
    "题型特征": ["多过程", "临界问题", "极值", "动态分析", "几何建模", "图像分析", "估算", "比例计算"],
    "物理场景": ["斜面", "弹簧", "传送带", "碰撞", "人船模型", "单杆模型", "双杆模型", "竖直圆轨道", "板块模型", "连接体", "流体模型"],
    "实验": ["实验数据处理", "实验误差分析", "实验器材选择", "电路设计", "纸带分析"],
    "数学工具": ["三角函数", "不等式", "二次函数极值", "平面几何"],
    "易错点": ["矢量方向", "正负号", "单位换算", "有效数字"],
}


def knowledge_points() -> list[dict[str, Any]]:
    return [
        {
            "topic1_id": topic1_id,
            "topic1_name": topic1_name,
            "topic2_id": topic2_id,
            "topic2_name": topic2_name,
            "topic3_id": f"{topic2_id}-{suffix}",
            "topic3_name": topic3_name,
            "source_chapter": f"{TEXTBOOK_EDITION}·{chapter}",
        }
        for topic1_id, topic1_name, topic2_id, topic2_name, topics in HIERARCHY
        for suffix, topic3_name, chapter in topics
    ]


def seed(db_path: Path) -> dict[str, int]:
    initialize_database(db_path)
    knowledge_result = MetadataManagementService(db_path).create_knowledge_points(knowledge_points())
    inserted_tags = 0
    with connect_db(db_path) as conn:
        for category, tags in TAG_CATALOG.items():
            for tag in tags:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO tag_catalog (tag_name, category, description, status)
                    VALUES (?, ?, NULL, 'active')
                    """,
                    (tag, category),
                )
                inserted_tags += max(cursor.rowcount, 0)
        conn.commit()
        total_knowledge = int(conn.execute("SELECT COUNT(*) FROM knowledge_points WHERE status='active'").fetchone()[0])
        total_tags = int(conn.execute("SELECT COUNT(*) FROM tag_catalog WHERE status='active'").fetchone()[0])
    return {
        "created_knowledge_points": int(knowledge_result["summary"]["created"]),
        "total_knowledge_points": total_knowledge,
        "created_tags": inserted_tags,
        "total_tags": total_tags,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Add missing standard knowledge points and tag catalog entries.")
    parser.add_argument("--db", type=Path, default=default_db_path())
    args = parser.parse_args()
    result = seed(args.db.resolve())
    print(f"database: {args.db.resolve()}")
    print(f"curriculum_standard: {CURRICULUM_STANDARD}")
    print(f"textbook_edition: {TEXTBOOK_EDITION}")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
