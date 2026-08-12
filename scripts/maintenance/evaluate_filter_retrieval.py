"""Evaluate deterministic year, region, type, and combined search filters."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
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


EXPECTED_YEARS = tuple(range(2007, 2027))
COMBINED_CASES = (
    {"case_id": "legacy_2007_national", "year": 2007, "region": "全国"},
    {"case_id": "legacy_2015_beijing", "year": 2015, "region": "北京"},
    {"case_id": "transition_2020_shandong", "year": 2020, "region": "山东"},
    {"case_id": "recent_2025_new_standard", "year": 2025, "region": "新课标"},
    {"case_id": "current_2026_guangdong", "year": 2026, "region": "广东"},
)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _search(
    service: QuestionSearchService,
    repository: QuestionSearchRepository,
    **filters: Any,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = service.search(
        QuestionSearchParams(search_mode=SearchMode.browse, limit=200, **filters),
        include_facets=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    items = [item.model_dump(mode="json") for item in response.items]
    full_rows = repository.get_questions_by_ids([item["question_id"] for item in items])
    rows = {str(row["question_id"]): row for row in full_rows}
    leaks: list[dict[str, Any]] = []
    for item in items:
        row = rows.get(str(item["question_id"]), {})
        if filters.get("year") is not None and item.get("year") != filters["year"]:
            leaks.append({"question_id": item["question_id"], "field": "year", "actual": item.get("year")})
        if filters.get("region") is not None and row.get("paper_region") != filters["region"]:
            leaks.append({"question_id": item["question_id"], "field": "region", "actual": row.get("paper_region")})
        if filters.get("question_type") is not None and item.get("question_type") != filters["question_type"]:
            leaks.append({"question_id": item["question_id"], "field": "question_type", "actual": item.get("question_type")})
    return {
        "filters": filters,
        "total": response.total,
        "returned": len(items),
        "leak_count": len(leaks),
        "leaks": leaks[:20],
    }, elapsed_ms


def evaluate() -> dict[str, Any]:
    repository = QuestionSearchRepository()
    service = QuestionSearchService(repository=repository)
    facets = repository.get_facets()
    latencies: list[float] = []
    year_cases: list[dict[str, Any]] = []
    for year in EXPECTED_YEARS:
        result, latency = _search(service, repository, year=year)
        latencies.append(latency)
        year_cases.append({"case_id": f"year_{year}", "latency_ms": round(latency, 2), **result})

    combined_cases: list[dict[str, Any]] = []
    for case in COMBINED_CASES:
        filters = {key: value for key, value in case.items() if key != "case_id"}
        result, latency = _search(service, repository, **filters)
        latencies.append(latency)
        combined_cases.append({"case_id": case["case_id"], "latency_ms": round(latency, 2), **result})

    type_cases: list[dict[str, Any]] = []
    for question_type in facets.get("question_types", []):
        result, latency = _search(service, repository, question_type=question_type)
        latencies.append(latency)
        type_cases.append({"case_id": f"type_{question_type}", "latency_ms": round(latency, 2), **result})

    all_cases = [*year_cases, *combined_cases, *type_cases]
    facet_years = {int(year) for year in facets.get("years", [])}
    metrics = {
        "year_case_count": len(year_cases),
        "earliest_year": min(facet_years) if facet_years else None,
        "latest_year": max(facet_years) if facet_years else None,
        "missing_expected_years": sorted(set(EXPECTED_YEARS) - facet_years),
        "empty_filter_case_count": sum(int(case["total"]) == 0 for case in all_cases),
        "filter_leak_count": sum(int(case["leak_count"]) for case in all_cases),
        "latency_mean_ms": round(statistics.fmean(latencies), 2),
        "latency_p95_ms": round(_percentile(latencies, 0.95), 2),
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "facets": {
            "years": facets.get("years", []),
            "regions": facets.get("regions", []),
            "question_types": facets.get("question_types", []),
        },
        "year_cases": year_cases,
        "combined_cases": combined_cases,
        "type_cases": type_cases,
    }


def check(report: dict[str, Any]) -> list[str]:
    metrics = report["metrics"]
    failures: list[str] = []
    if metrics["missing_expected_years"]:
        failures.append(f"missing_expected_years={metrics['missing_expected_years']}")
    if int(metrics["empty_filter_case_count"]) > 0:
        failures.append(f"empty_filter_case_count={metrics['empty_filter_case_count']} > 0")
    if int(metrics["filter_leak_count"]) > 0:
        failures.append(f"filter_leak_count={metrics['filter_leak_count']} > 0")
    if float(metrics["latency_p95_ms"]) > 1000:
        failures.append(f"latency_p95_ms={metrics['latency_p95_ms']:.1f} > 1000")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "retrieval-quality" / "filter-latest.json",
    )
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"report: {args.output}")
    failures = check(report)
    if failures:
        print("Filter retrieval quality gate failed:")
        for failure in failures:
            print(f"- {failure}")
    return 1 if args.check and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
