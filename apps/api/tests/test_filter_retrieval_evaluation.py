from __future__ import annotations

from scripts.maintenance.evaluate_filter_retrieval import COMBINED_CASES, EXPECTED_YEARS, check


def test_filter_benchmark_covers_legacy_and_current_years() -> None:
    assert EXPECTED_YEARS[0] == 2007
    assert EXPECTED_YEARS[-1] == 2026
    case_years = {int(case["year"]) for case in COMBINED_CASES}
    assert {2007, 2015, 2020, 2025, 2026} <= case_years


def test_filter_quality_gate_rejects_missing_empty_or_leaking_results() -> None:
    healthy = {
        "metrics": {
            "missing_expected_years": [],
            "empty_filter_case_count": 0,
            "filter_leak_count": 0,
            "latency_p95_ms": 200.0,
        }
    }
    assert check(healthy) == []

    degraded = {
        "metrics": {
            "missing_expected_years": [2012],
            "empty_filter_case_count": 1,
            "filter_leak_count": 2,
            "latency_p95_ms": 1200.0,
        }
    }
    failures = check(degraded)
    assert len(failures) == 4
