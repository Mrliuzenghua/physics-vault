from __future__ import annotations

from physics_vault_api.services.retrieval_method_intent import (
    detect_method_intent,
    expand_method_query,
    score_method_candidate,
)


def test_gravity_velocity_compensation_finds_classic_structure_without_method_name() -> None:
    row = {
        "question_id": "Q00000298",
        "stem_text": (
            "在水平匀强磁场中，一质量为m、带正电q的小球在O点静止释放，"
            "运动曲线最低点的曲率半径为该点下降距离的2倍，重力加速度为g。"
        ),
        "analysis_text": "洛伦兹力不做功，由动能定理得mgy=mv²/2。",
        "topic3": "圆周运动",
    }

    match = score_method_candidate("重力配速法", row)

    assert match is not None
    assert match["branch"] == "gravity"
    assert match["level"] == "structural"
    assert match["score"] >= 0.9
    assert any("静止释放" in evidence for evidence in match["evidence"])
    assert score_method_candidate("电场配速法", row) is None


def test_gravity_method_query_rejects_questions_that_explicitly_ignore_gravity() -> None:
    row = {
        "stem_text": "电子进入正交电磁场，不计重力及电子间相互作用。",
        "analysis_text": "电场力大于洛伦兹力，根据动能定理求解。",
    }

    assert score_method_candidate("重力配速法", row) is None


def test_gravity_method_query_handles_clause_level_gravity_negation() -> None:
    row = {
        "stem_text": (
            "电子在磁场中运动，不计电子之间的相互作用及电子的重力。"
        ),
        "analysis_text": "将速度分解为匀速直线运动和匀速圆周运动。",
    }

    assert score_method_candidate("重力配速法", row) is None


def test_gravity_method_requires_balance_or_classic_release_anchor() -> None:
    row = {
        "stem_text": (
            "带正电小球在电场和磁场中运动，重力加速度为g，求最大距离。"
        ),
        "analysis_text": (
            "将运动分解后求解；洛伦兹力提供向心力qvB=mv²/R。"
        ),
    }

    match = score_method_candidate("重力配速法", row)

    assert match is not None
    assert match["level"] == "related"


def test_generic_method_query_classifies_explicit_electric_branch() -> None:
    row = {
        "stem_text": "带电粒子进入正交电磁场。",
        "analysis_text": (
            "由配速法，将速度分解，使qBv=qE；一个分速度做匀速直线运动，"
            "另一个分速度对应匀速圆周运动。"
        ),
    }

    match = score_method_candidate("帮我找配速法题目", row)

    assert match is not None
    assert match["branch"] == "electric"
    assert match["level"] == "explicit"


def test_method_query_expansion_explains_formula_and_scene() -> None:
    intent = detect_method_intent("重力配速法")

    assert intent is not None
    assert intent.branches == ("gravity",)
    expanded = expand_method_query("重力配速法", intent)
    assert "qvB=mg" in expanded
    assert "曲率半径" in expanded


def test_reference_drift_solution_is_a_structural_electric_method_match() -> None:
    row = {
        "stem_text": "带电粒子在相互垂直的匀强电场和匀强磁场中运动。",
        "analysis_text": (
            "设粒子恰好沿x方向匀速运动的速度大小为v1，则有qv1B=qE。"
            "其他粒子在一个周期内沿x方向前进相同距离。"
        ),
    }

    match = score_method_candidate("电场配速法", row)

    assert match is not None
    assert match["branch"] == "electric"
    assert match["level"] == "structural"


def test_method_tag_is_not_misreported_as_literal_content_match() -> None:
    row = {
        "stem_text": (
            "水平匀强磁场中，带正电小球从O点静止释放，求运动曲线最低点。"
            "重力加速度为g。"
        ),
        "analysis_text": "洛伦兹力不做功，由动能定理和最低点曲率半径求解。",
        "tags_json": '["配速法"]',
    }

    match = score_method_candidate("重力配速法", row)

    assert match is not None
    assert match["level"] == "structural"
    assert match["match_basis"] == "method_tag"
    assert match["evidence"][0] == "方法标签：配速法"


def test_electric_method_does_not_join_evidence_from_different_subquestions() -> None:
    row = {
        "stem_text": "带电粒子在正交电磁场中运动。",
        "analysis_text": (
            "（1）把另一段机械运动的速度进行分解。\n\n"
            "（2）某一时刻洛伦兹力与电场力平衡，qvB=qE。"
        ),
    }

    match = score_method_candidate("电场配速法", row)

    assert match is not None
    assert match["level"] == "related"
