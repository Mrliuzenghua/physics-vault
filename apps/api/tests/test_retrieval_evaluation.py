from __future__ import annotations

from scripts.maintenance.evaluate_question_retrieval import (
    BENCHMARK_CASES,
    _is_relevant,
    _passes_thresholds,
    _percentile,
)


def test_benchmark_covers_major_physics_domains() -> None:
    case_ids = {case.case_id for case in BENCHMARK_CASES}

    assert len(case_ids) >= 18
    assert {
        "collision",
        "electric_deflection",
        "gravity_velocity_compensation",
        "total_internal_reflection",
        "ideal_gas",
        "photoelectric",
        "wave_graph",
    } <= case_ids


def test_relevance_accepts_structured_topic_or_content_evidence() -> None:
    case = next(item for item in BENCHMARK_CASES if item.case_id == "electric_deflection")
    labelled = {
        "knowledge_points": [{"topic3_id": "KP-EM-EFIELD-PARTICLE"}],
        "stem_text": "unrelated",
    }
    mislabeled_but_relevant = {
        "knowledge_points": [{"topic3_id": "KP-MECH-KIN-PROJECTILE"}],
        "stem_text": "一个带电粒子进入匀强电场后发生偏转。",
    }
    irrelevant = {
        "knowledge_points": [{"topic3_id": "KP-EM-MAGNETIC-PARTICLE"}],
        "stem_text": "带电粒子只在磁场中做圆周运动。",
    }

    assert _is_relevant(case, labelled) == (True, "topic")
    assert _is_relevant(case, mislabeled_but_relevant) == (True, "content")
    assert _is_relevant(case, irrelevant) == (False, "none")


def test_quality_gate_rejects_index_or_ranking_regressions() -> None:
    healthy = {
        "metrics": {
            "embedding_coverage": 1.0,
            "hit_at_3": 1.0,
            "hit_at_10": 1.0,
            "precision_at_5": 0.98,
            "mrr": 1.0,
            "latency_p95_ms": 5500.0,
        }
    }
    degraded = {
        "metrics": {
            **healthy["metrics"],
            "embedding_coverage": 0.80,
            "hit_at_10": 0.90,
        }
    }

    assert _passes_thresholds(healthy) == (True, [])
    passed, failures = _passes_thresholds(degraded)
    assert passed is False
    assert any("embedding_coverage" in failure for failure in failures)
    assert any("hit_at_10" in failure for failure in failures)


def test_percentile_uses_a_conservative_observed_value() -> None:
    assert _percentile([100.0, 200.0, 300.0, 400.0], 0.95) == 400.0
