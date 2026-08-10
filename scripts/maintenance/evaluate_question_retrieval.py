"""Evaluate real question retrieval quality against a small physics benchmark.

This is intentionally an online evaluation: hybrid mode calls the configured
embedding and rerank providers, then judges returned questions by both their
structured topic labels and evidence in the actual question content.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_SOURCE = PROJECT_ROOT / "apps" / "api" / "src"
if str(API_SOURCE) not in sys.path:
    sys.path.insert(0, str(API_SOURCE))

from physics_vault_api.repositories.question_search import QuestionSearchRepository  # noqa: E402
from physics_vault_api.schemas.question_search import QuestionSearchParams, SearchMode  # noqa: E402
from physics_vault_api.services.question_search import QuestionSearchService  # noqa: E402
from physics_vault_api.services.embedding_runtime import resolve_embedding_model  # noqa: E402


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    query: str
    expected_topic3_ids: tuple[str, ...]
    evidence_groups: tuple[tuple[str, ...], ...]


BENCHMARK_CASES = (
    BenchmarkCase(
        "kinematics_vt",
        "小车做匀加速直线运动，根据 v-t 图像求加速度",
        ("KP-MECH-KIN-VT",),
        (("v-t", "加速度"), ("速度时间图像", "加速度"), ("匀变速", "加速度")),
    ),
    BenchmarkCase(
        "collision",
        "两个物体碰撞后粘在一起，求共同速度",
        ("KP-MECH-MOMENTUM-COLLISION", "KP-MECH-MOMENTUM-CONSERVATION"),
        (("碰撞", "速度"), ("粘", "共同速度"), ("动量守恒", "速度")),
    ),
    BenchmarkCase(
        "newton_second_law",
        "斜面上物体受力，应用牛顿第二定律求加速度",
        ("KP-MECH-DYN-NEWTON2",),
        (("斜面", "加速度"), ("牛顿第二定律",)),
    ),
    BenchmarkCase(
        "satellite_orbit",
        "卫星绕行星做圆周运动，比较轨道速度和周期",
        ("KP-MECH-GRAVITY-ORBIT",),
        (("卫星", "轨道"), ("卫星", "周期"), ("环绕", "周期")),
    ),
    BenchmarkCase(
        "electric_deflection",
        "带电粒子进入匀强电场发生偏转",
        ("KP-EM-EFIELD-PARTICLE",),
        (("带电粒子", "电场"), ("电子", "偏转"), ("电场", "偏转")),
    ),
    BenchmarkCase(
        "magnetic_particle",
        "带电粒子垂直进入匀强磁场做圆周运动",
        ("KP-EM-MAGNETIC-PARTICLE", "KP-EM-MAGNETIC-LORENTZ"),
        (("带电粒子", "磁场"), ("洛伦兹力", "半径")),
    ),
    BenchmarkCase(
        "gravity_velocity_compensation",
        "重力配速法经典题：带电小球在水平匀强磁场中从静止释放",
        ("KP-EM-MAGNETIC-COMBINED", "KP-EM-MAGNETIC-LORENTZ"),
        (
            ("带正电", "水平匀强磁场", "静止释放", "曲率半径"),
            ("洛伦兹力", "重力", "最大距离"),
            ("洛伦兹力", "重力平衡"),
        ),
    ),
    BenchmarkCase(
        "motional_emf",
        "导体棒切割磁感线产生感应电动势",
        ("KP-EM-INDUCTION-ROD",),
        (("导体棒", "感应电动势"), ("切割磁感线",)),
    ),
    BenchmarkCase(
        "transformer",
        "理想变压器原副线圈电压和电流的关系",
        ("KP-EM-AC-TRANSFORMER",),
        (("变压器", "原线圈"), ("变压器", "副线圈"), ("匝数", "电压")),
    ),
    BenchmarkCase(
        "power_supply_experiment",
        "测量电源电动势和内阻的实验，处理 U-I 图像",
        ("KP-EM-CIRCUIT-EXPERIMENT",),
        (("电动势", "内阻"), ("U-I", "电源"), ("伏安法", "内阻")),
    ),
    BenchmarkCase(
        "total_internal_reflection",
        "光纤中的全反射和临界角",
        ("KP-OPTICS-GEOMETRY-TOTAL",),
        (("全反射", "临界角"), ("光纤", "全反射")),
    ),
    BenchmarkCase(
        "double_slit",
        "双缝干涉条纹间距",
        ("KP-OPTICS-PHYSICAL-INTERFERENCE",),
        (("双缝", "条纹"), ("干涉", "条纹间距")),
    ),
    BenchmarkCase(
        "ideal_gas",
        "一定质量理想气体等温变化时压强和体积的关系",
        ("KP-THERMO-GAS-STATE", "KP-THERMO-GAS-BOYLE"),
        (("理想气体", "等温"), ("压强", "体积", "等温")),
    ),
    BenchmarkCase(
        "first_law",
        "气体吸热并对外做功时内能如何变化",
        ("KP-THERMO-LAW-FIRST",),
        (("吸热", "做功", "内能"), ("热力学第一定律",)),
    ),
    BenchmarkCase(
        "photoelectric",
        "光电效应中的截止电压和逸出功",
        ("KP-MODERN-ATOM-PHOTOELECTRIC",),
        (("光电效应", "截止电压"), ("光电子", "逸出功")),
    ),
    BenchmarkCase(
        "bohr_model",
        "氢原子能级跃迁并发射光子",
        ("KP-MODERN-ATOM-BOHR",),
        (("氢原子", "能级"), ("跃迁", "光子")),
    ),
    BenchmarkCase(
        "wave_graph",
        "机械波传播中波形图和质点振动图像的关系",
        ("KP-WAVE-MECHANICAL-IMAGE", "KP-WAVE-MECHANICAL-PROPAGATION"),
        (("波形图", "振动图像"), ("机械波", "质点", "振动")),
    ),
    BenchmarkCase(
        "pendulum",
        "单摆周期与摆长、重力加速度的关系",
        ("KP-MECH-OSC-PENDULUM",),
        (("单摆", "周期"), ("摆长", "重力加速度")),
    ),
    BenchmarkCase(
        "lenz_law",
        "用楞次定律判断感应电流方向",
        ("KP-EM-INDUCTION-LENZ",),
        (("楞次定律", "方向"), ("感应电流", "方向")),
    ),
)


def _normalise(text: Any) -> str:
    return "".join(character.casefold() for character in str(text or "") if character.isalnum())


def _topic_ids(row: dict[str, Any]) -> set[str]:
    return {
        str(point.get("topic3_id"))
        for point in row.get("knowledge_points", [])
        if isinstance(point, dict) and point.get("topic3_id")
    }


def _content(row: dict[str, Any]) -> str:
    fields = (
        "canonical_title",
        "title_text",
        "stem_text",
        "answer_text",
        "analysis_text",
        "topic2",
        "topic3",
    )
    labels = " ".join(
        str(point.get("topic3_name") or "")
        for point in row.get("knowledge_points", [])
        if isinstance(point, dict)
    )
    return _normalise(" ".join(str(row.get(field) or "") for field in fields) + " " + labels)


def _is_relevant(case: BenchmarkCase, row: dict[str, Any]) -> tuple[bool, str]:
    expected = set(case.expected_topic3_ids)
    if expected & _topic_ids(row):
        return True, "topic"
    content = _content(row)
    for group in case.evidence_groups:
        if all(_normalise(term) in content for term in group):
            return True, "content"
    return False, "none"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def evaluate(mode: SearchMode, *, limit: int = 10) -> dict[str, Any]:
    repository = QuestionSearchRepository()
    service = QuestionSearchService(repository=repository)
    cases: list[dict[str, Any]] = []
    latencies: list[float] = []

    provider = os.getenv("PHYSICS_VAULT_EMBEDDING_PROVIDER", "openai").strip().lower()
    configured_model = os.getenv(
        "PHYSICS_VAULT_EMBEDDING_MODEL", "text-embedding-3-small"
    ).strip()
    model_name = resolve_embedding_model(provider, configured_model)
    model_version = os.getenv("PHYSICS_VAULT_EMBEDDING_MODEL_VERSION", "").strip()
    vector_type = os.getenv(
        "PHYSICS_VAULT_EMBEDDING_VECTOR_TYPE", "semantic_search"
    ).strip()
    index_health = repository.embedding_index_health(
        model_name=model_name,
        model_version=model_version,
        vector_type=vector_type,
    )
    question_count = int(index_health["question_count"])
    ready_count = int(index_health["ready_embedding_count"])
    embedding_coverage = ready_count / question_count if question_count else 0.0

    for index, case in enumerate(BENCHMARK_CASES, start=1):
        started = time.perf_counter()
        response = service.search(
            QuestionSearchParams(search_mode=mode, query=case.query, limit=limit),
            include_facets=False,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)

        ids = [item.question_id for item in response.items]
        rows = repository.get_questions_by_ids(ids)
        rows_by_id = {str(row["question_id"]): row for row in rows}
        judgements: list[dict[str, Any]] = []
        for rank, question_id in enumerate(ids, start=1):
            row = rows_by_id.get(question_id, {})
            relevant, reason = _is_relevant(case, row)
            judgements.append(
                {
                    "rank": rank,
                    "question_id": question_id,
                    "relevant": relevant,
                    "reason": reason,
                    "topic3_ids": sorted(_topic_ids(row)),
                    "title": str(row.get("title_text") or row.get("canonical_title") or "")[:100],
                }
            )

        relevant_ranks = [item["rank"] for item in judgements if item["relevant"]]
        reciprocal_rank = 1.0 / relevant_ranks[0] if relevant_ranks else 0.0
        case_result = {
            **asdict(case),
            "latency_ms": round(elapsed_ms, 1),
            "hit_at_3": any(rank <= 3 for rank in relevant_ranks),
            "hit_at_10": bool(relevant_ranks),
            "precision_at_5": sum(
                1 for item in judgements[:5] if item["relevant"]
            )
            / min(5, max(len(judgements), 1)),
            "reciprocal_rank": reciprocal_rank,
            "results": judgements,
        }
        cases.append(case_result)
        top_relevant = relevant_ranks[0] if relevant_ranks else "-"
        print(
            f"[{index:02d}/{len(BENCHMARK_CASES)}] {case.case_id:<28} "
            f"first={top_relevant!s:<2} p@5={case_result['precision_at_5']:.2f} "
            f"{elapsed_ms:7.0f} ms",
            flush=True,
        )

    count = len(cases)
    metrics = {
        "case_count": count,
        "embedding_coverage": embedding_coverage,
        "hit_at_3": sum(item["hit_at_3"] for item in cases) / count,
        "hit_at_10": sum(item["hit_at_10"] for item in cases) / count,
        "precision_at_5": statistics.fmean(item["precision_at_5"] for item in cases),
        "mrr": statistics.fmean(item["reciprocal_rank"] for item in cases),
        "latency_mean_ms": statistics.fmean(latencies),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode.value,
        "index": {
            "model_name": model_name,
            "vector_type": vector_type,
            "question_count": question_count,
            "ready_embedding_count": ready_count,
            "stale_embedding_count": index_health["stale_embedding_count"],
            "missing_embedding_count": index_health["missing_embedding_count"],
            "last_updated_at": index_health["last_updated_at"],
        },
        "metrics": {key: round(value, 4) for key, value in metrics.items()},
        "cases": cases,
    }


def _passes_thresholds(report: dict[str, Any]) -> tuple[bool, list[str]]:
    metrics = report["metrics"]
    failures: list[str] = []
    thresholds = {
        "embedding_coverage": 0.99,
        "hit_at_3": 0.94,
        "hit_at_10": 1.00,
        "precision_at_5": 0.90,
        "mrr": 0.94,
    }
    for name, minimum in thresholds.items():
        if float(metrics[name]) < minimum:
            failures.append(f"{name}={metrics[name]:.3f} < {minimum:.3f}")
    if float(metrics["latency_p95_ms"]) > 8000:
        failures.append(
            f"latency_p95_ms={metrics['latency_p95_ms']:.1f} > 8000.0"
        )
    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["strict", "hybrid", "similar"], default="hybrid")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "retrieval-quality" / "latest.json",
    )
    parser.add_argument("--check", action="store_true", help="Fail if quality thresholds regress")
    args = parser.parse_args()

    report = evaluate(SearchMode(args.mode), limit=max(3, min(args.limit, 20)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics = report["metrics"]
    print("\nRetrieval quality summary")
    for name, value in metrics.items():
        print(f"  {name}: {value}")
    print(f"  report: {args.output}")

    passed, failures = _passes_thresholds(report)
    if failures:
        print("  threshold failures:")
        for failure in failures:
            print(f"    - {failure}")
    return 1 if args.check and not passed else 0


if __name__ == "__main__":
    raise SystemExit(main())
