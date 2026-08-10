"""Evaluate method-specific MCP retrieval against curated positives and hard negatives."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
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

from physics_vault_api.services.method_feature_index import (  # noqa: E402
    method_feature_index_health,
)
from physics_vault_api.services.retrieval_learning import (  # noqa: E402
    load_method_feedback_constraints,
)


@dataclass(frozen=True)
class MethodBenchmarkCase:
    case_id: str
    query: str
    required_question_ids: tuple[str, ...]
    hard_negative_question_ids: tuple[str, ...]
    expected_top1: str


CASES = (
    MethodBenchmarkCase(
        "gravity_velocity_compensation",
        "重力配速法",
        ("Q00000298",),
        ("Q00000594", "Q00002593", "Q00003232", "Q00004600"),
        "Q00000298",
    ),
    MethodBenchmarkCase(
        "electric_velocity_compensation",
        "电场配速法",
        (
            "Q00004694",
            "Q00004786",
            "Q00004019",
            "Q00004586",
            "Q00004974",
            "Q00000983",
        ),
        ("Q00000298",),
        "Q00004694",
    ),
    MethodBenchmarkCase(
        "generic_velocity_compensation",
        "配速法",
        (
            "Q00000298",
            "Q00004694",
            "Q00004786",
            "Q00004019",
            "Q00004586",
            "Q00004974",
            "Q00000983",
        ),
        ("Q00000594", "Q00002593", "Q00003232", "Q00004600"),
        "Q00004694",
    ),
)


def _load_mcp_module() -> Any:
    path = PROJECT_ROOT / "scripts" / "physics_vault_mcp_server.py"
    spec = importlib.util.spec_from_file_location("physics_vault_method_benchmark", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 physics_vault MCP。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def evaluate(limit: int = 20) -> dict[str, Any]:
    module = _load_mcp_module()
    # Warm the module and verify the derived index before measuring latency.
    module.search_method_questions("配速法", limit=1)
    cases: list[dict[str, Any]] = []
    latencies: list[float] = []
    for case in CASES:
        started = time.perf_counter()
        result = module.search_method_questions(case.query, limit=limit)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        ids = [str(item.get("question_id")) for item in result.get("items", [])]
        levels = [str(item.get("method_level")) for item in result.get("items", [])]
        required = set(case.required_question_ids)
        found_required = required.intersection(ids[:10])
        hard_negative_hits = sorted(set(case.hard_negative_question_ids).intersection(ids))
        cases.append(
            {
                **asdict(case),
                "latency_ms": round(elapsed_ms, 2),
                "top_ids": ids[:10],
                "top1_correct": bool(ids) and ids[0] == case.expected_top1,
                "required_recall_at_10": len(found_required) / max(len(required), 1),
                "missing_required_ids": sorted(required - found_required),
                "hard_negative_hits": hard_negative_hits,
                "related_visible_count": sum(level == "related" for level in levels),
                "response_mode": result.get("response_mode"),
                "confirmed_only": (result.get("method_search") or {}).get("confirmed_only"),
            }
        )

    feedback_cases: list[dict[str, Any]] = []
    feedback_positive_total = 0
    feedback_positive_found = 0
    feedback_negative_hits = 0
    for constraint in load_method_feedback_constraints():
        started = time.perf_counter()
        result = module.search_method_questions(
            constraint["query"],
            limit=50,
            confirmed_only=True,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        ids = [str(item.get("question_id")) for item in result.get("items", [])]
        positives = set(constraint["positive_question_ids"])
        negatives = set(constraint["negative_question_ids"])
        found_positives = positives.intersection(ids)
        hit_negatives = negatives.intersection(ids)
        feedback_positive_total += len(positives)
        feedback_positive_found += len(found_positives)
        feedback_negative_hits += len(hit_negatives)
        feedback_cases.append(
            {
                **constraint,
                "latency_ms": round(elapsed_ms, 2),
                "top_ids": ids[:10],
                "positive_found_ids": sorted(found_positives),
                "missing_positive_ids": sorted(positives - found_positives),
                "negative_hit_ids": sorted(hit_negatives),
                "positive_recall_at_50": (
                    len(found_positives) / len(positives) if positives else 1.0
                ),
            }
        )

    health = method_feature_index_health()
    metrics = {
        "case_count": len(cases),
        "top1_accuracy": statistics.fmean(float(case["top1_correct"]) for case in cases),
        "required_recall_at_10": statistics.fmean(case["required_recall_at_10"] for case in cases),
        "hard_negative_violation_count": sum(len(case["hard_negative_hits"]) for case in cases),
        "related_visible_count": sum(case["related_visible_count"] for case in cases),
        "latency_mean_ms": statistics.fmean(latencies),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "method_index_coverage": (
            int(health["ready_count"]) / max(int(health["question_count"]), 1)
        ),
        "feedback_constraint_case_count": len(feedback_cases),
        "feedback_positive_count": feedback_positive_total,
        "feedback_positive_recall_at_50": (
            feedback_positive_found / feedback_positive_total
            if feedback_positive_total
            else 1.0
        ),
        "feedback_negative_violation_count": feedback_negative_hits,
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "index": health,
        "cases": cases,
        "feedback_cases": feedback_cases,
    }


def _check(report: dict[str, Any]) -> list[str]:
    metrics = report["metrics"]
    failures: list[str] = []
    thresholds = {
        "top1_accuracy": 1.0,
        "required_recall_at_10": 1.0,
        "method_index_coverage": 0.99,
    }
    for name, minimum in thresholds.items():
        if float(metrics[name]) < minimum:
            failures.append(f"{name}={metrics[name]:.4f} < {minimum:.4f}")
    if int(metrics["hard_negative_violation_count"]) > 0:
        failures.append(
            f"hard_negative_violation_count={metrics['hard_negative_violation_count']} > 0"
        )
    if int(metrics["related_visible_count"]) > 0:
        failures.append(f"related_visible_count={metrics['related_visible_count']} > 0")
    if float(metrics["latency_p95_ms"]) > 250:
        failures.append(f"latency_p95_ms={metrics['latency_p95_ms']:.1f} > 250")
    if float(metrics.get("feedback_positive_recall_at_50", 1.0)) < 1.0:
        failures.append(
            "feedback_positive_recall_at_50="
            f"{metrics['feedback_positive_recall_at_50']:.4f} < 1.0000"
        )
    if int(metrics.get("feedback_negative_violation_count", 0)) > 0:
        failures.append(
            "feedback_negative_violation_count="
            f"{metrics['feedback_negative_violation_count']} > 0"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "retrieval-quality" / "method-latest.json",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = evaluate(limit=min(max(args.limit, 10), 50))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"report: {args.output}")
    if args.check:
        failures = _check(report)
        if failures:
            print("Method retrieval quality gate failed:")
            for failure in failures:
                print(f"- {failure}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
