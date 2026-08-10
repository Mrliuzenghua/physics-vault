"""Method-aware query expansion and evidence scoring for physics retrieval.

Knowledge-point labels describe what a question is about. Teachers also search
by solution methods whose names may never occur in the stem or explanation.
This module keeps those method signatures explicit and explainable instead of
asking a dense vector or a language model to infer them from labels alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MethodIntent:
    method_id: str
    method_name: str
    branches: tuple[str, ...]
    expanded_terms: tuple[str, ...]


_NEGATED_GRAVITY_RE = re.compile(
    r"(?:不计|忽略|不考虑)(?:粒子|小球|物体|电子|离子)?(?:的)?(?:所受的?)?重力"
)
_NEGATED_GRAVITY_CLAUSE_RE = re.compile(
    r"(?:不计|忽略|不考虑)[^，。；;,\n]{0,40}重力"
)
_FORMULA_SPACE_RE = re.compile(r"[\s${}\\_\[\]()<>=，。；、:：]+")
_EQUATION_SPACE_RE = re.compile(r"[\s${}\\_\[\](),，。；、:：]+")


def detect_method_intent(query: str) -> MethodIntent | None:
    clean = str(query or "").strip()
    compact = _compact(clean)
    method_trigger = any(
        term in compact
        for term in (
            "配速法",
            "配速",
            "漂移速度法",
            "洛伦兹力分力平衡",
            "洛伦兹力与重力平衡",
            "速度分解洛伦兹力",
        )
    )
    if not method_trigger:
        return None

    mentions_gravity = "重力" in compact or "mg" in compact.casefold()
    mentions_electric = "电场力" in compact or "电场配速" in compact
    if mentions_gravity and not mentions_electric:
        branches = ("gravity",)
    elif mentions_electric and not mentions_gravity:
        branches = ("electric",)
    else:
        branches = ("gravity", "electric")

    terms: list[str] = ["配速法", "速度分解", "洛伦兹力", "匀速圆周运动"]
    if "gravity" in branches:
        terms.extend(
            [
                "水平匀强磁场",
                "带电小球",
                "重力",
                "静止释放",
                "运动曲线",
                "曲率半径",
                "最低点",
                "最大距离",
                "qvB=mg",
            ]
        )
    if "electric" in branches:
        terms.extend(
            [
                "正交电磁场",
                "电场力与洛伦兹力平衡",
                "匀速直线运动",
                "旋进运动",
                "摆线",
                "qvB=qE",
                "v=E/B",
            ]
        )
    return MethodIntent(
        method_id="velocity_compensation",
        method_name="配速法",
        branches=branches,
        expanded_terms=tuple(dict.fromkeys(terms)),
    )


def expand_method_query(query: str, intent: MethodIntent | None = None) -> str:
    intent = intent or detect_method_intent(query)
    if intent is None:
        return str(query or "").strip()
    if intent.branches == ("gravity",):
        definition = (
            "重力配速法：带电小球在磁场和重力作用下运动，选取满足 qvB=mg "
            "的参考速度，把运动分解为匀速漂移和匀速圆周运动；典型题干可能只写"
            "静止释放、运动曲线、最低点、曲率半径或最大下降距离。"
        )
    elif intent.branches == ("electric",):
        definition = (
            "电场配速法：在正交电磁场中选取满足 qvB=qE、v=E/B 的参考速度，"
            "把运动分解为匀速直线运动和匀速圆周运动。"
        )
    else:
        definition = (
            "配速法：选择一个速度分量，使其洛伦兹力与恒定的重力或电场力平衡，"
            "剩余速度分量对应匀速圆周运动。重力分支满足 qvB=mg，"
            "电场分支满足 qvB=qE。"
        )
    return f"{str(query or '').strip()}\n{definition}"


def method_query_terms(query: str) -> list[str]:
    intent = detect_method_intent(query)
    return list(intent.expanded_terms) if intent else []


def score_method_candidate(
    query: str,
    row: dict[str, Any],
    *,
    intent: MethodIntent | None = None,
) -> dict[str, Any] | None:
    intent = intent or detect_method_intent(query)
    if intent is None:
        return None

    body_text = _candidate_body_text(row)
    metadata_text = _candidate_metadata_text(row)
    windows = _candidate_windows(row) or [body_text]
    explicit_in_content = any(
        term in _compact(body_text) for term in ("配速法", "漂移速度法")
    )
    explicit_in_metadata = any(
        term in _compact(metadata_text) for term in ("配速法", "漂移速度法")
    )

    branch_scores: dict[str, float] = {}
    branch_evidence: dict[str, list[str]] = {}
    if "gravity" in intent.branches:
        score, evidence = _best_window_score(windows, _score_gravity_signature)
        branch_scores["gravity"] = score
        branch_evidence["gravity"] = evidence
    if "electric" in intent.branches:
        score, evidence = _best_window_score(windows, _score_electric_signature)
        branch_scores["electric"] = score
        branch_evidence["electric"] = evidence

    branch = max(branch_scores, key=branch_scores.get)
    score = branch_scores[branch]
    if explicit_in_content and score >= 0.50:
        score = 1.0
        level = "explicit"
        match_basis = "content"
    elif explicit_in_metadata and score >= 0.78:
        # A curated method tag is a strong retrieval signal, but it must not be
        # reported as though the stem or analysis literally named the method.
        score = max(score, 0.85)
        level = "structural"
        match_basis = "method_tag"
    elif score >= 0.78:
        level = "structural"
        match_basis = "structure"
    elif score >= 0.50:
        level = "related"
        match_basis = "structure"
    else:
        return None

    evidence = list(branch_evidence.get(branch, []))
    if explicit_in_content:
        evidence.insert(0, _evidence_snippet(body_text, "配速法"))
    elif explicit_in_metadata:
        evidence.insert(0, "方法标签：配速法")
    return {
        "method_id": intent.method_id,
        "method_name": intent.method_name,
        "branch": branch,
        "level": level,
        "match_basis": match_basis,
        "score": round(min(score, 1.0), 4),
        "evidence": list(dict.fromkeys(item for item in evidence if item))[:3],
    }


def _score_gravity_signature(
    text: str,
    compact: str,
    formula_text: str,
) -> tuple[float, list[str]]:
    without_negation = _NEGATED_GRAVITY_RE.sub("", text)
    without_negation = _NEGATED_GRAVITY_CLAUSE_RE.sub("", without_negation)
    compact_without_negation = _compact(without_negation)
    has_magnetic = any(term in compact for term in ("磁场", "磁感应强度", "洛伦兹力"))
    has_charged_body = any(
        term in compact
        for term in ("带电小球", "带电粒子", "带正电", "带负电", "电荷量", "电量")
    )
    has_mg_formula = _has_mg_formula(without_negation)
    has_effective_gravity = "重力" in compact_without_negation or has_mg_formula
    has_motion_signature = any(
        term in compact
        for term in (
            "静止释放",
            "运动曲线",
            "曲率半径",
            "最低点",
            "第一次下降",
            "最大距离",
            "最大下降",
        )
    )
    has_magnetic_formula = (
        "qvb" in formula_text
        or "bqv" in formula_text
        or "qbv" in formula_text
        or "洛伦兹力" in compact
    )
    has_velocity_split = _has_velocity_split(compact)
    has_direct_balance = _has_qvb_equals_mg(text) or any(
        term in compact
        for term in (
            "洛伦兹力与重力平衡",
            "洛伦兹力和重力平衡",
            "洛伦兹力跟重力平衡",
            "洛伦兹力平衡重力",
        )
    )
    has_classic_release_curve = (
        "静止释放" in compact
        and any(term in compact for term in ("运动曲线", "曲率半径", "最大下降", "最大距离"))
        and has_charged_body
        and has_magnetic_formula
    )

    if not has_effective_gravity:
        return 0.0, []

    score = 0.0
    evidence: list[str] = []
    if has_magnetic:
        score += 0.20
    if has_charged_body:
        score += 0.15
    if has_effective_gravity:
        score += 0.20
        evidence.append(_evidence_snippet(without_negation, "重力"))
    if has_magnetic and has_charged_body and has_effective_gravity:
        score += 0.10
    if has_motion_signature:
        score += 0.05
        for term in ("静止释放", "运动曲线", "曲率半径", "最低点", "最大距离"):
            if term in compact:
                evidence.append(_evidence_snippet(text, term))
                break
    if has_magnetic_formula and has_mg_formula:
        score += 0.05
        evidence.append(_evidence_snippet(text, "洛伦兹力"))
    if has_direct_balance:
        score += 0.25
        evidence.append(_evidence_snippet(text, "洛伦兹力与重力平衡"))
    if has_classic_release_curve:
        score += 0.25
    if has_velocity_split:
        score += 0.25
        evidence.append(_evidence_snippet(text, "分解"))
    if not (has_direct_balance or has_classic_release_curve):
        # Gravity, a magnetic field and even a generic velocity decomposition
        # can coexist in many multipart questions.  A confirmed gravity-method
        # match additionally needs qvB=mg (literal or verbal) or the classic
        # charged-body release/curve signature; otherwise keep it “related”.
        score = min(score, 0.70)
    return min(score, 1.0), evidence


def _score_electric_signature(
    text: str,
    compact: str,
    formula_text: str,
) -> tuple[float, list[str]]:
    has_magnetic = any(term in compact for term in ("磁场", "磁感应强度", "洛伦兹力"))
    has_electric_force_formula = _has_qe_formula(text)
    has_electric = any(
        term in compact for term in ("电场", "电场力", "电场强度")
    ) or has_electric_force_formula
    has_charged_body = any(
        term in compact
        for term in ("带电", "带正电", "带负电", "电子", "离子", "电荷量", "电量")
    )
    has_velocity_split = _has_velocity_split(compact)
    has_electric_balance_formula = _has_qvb_equals_qe(text)
    has_balance = (
        ("洛伦兹力" in compact and "电场力" in compact and "平衡" in compact)
        or has_electric_balance_formula
        or "e/b" in formula_text
    )
    has_reference_drift = has_balance and (
        ("恰好沿" in compact and "匀速运动" in compact)
        or ("设粒子" in compact and "匀速运动的速度" in compact)
    )
    has_superposition = any(
        term in compact
        for term in ("匀速直线运动", "匀速圆周运动", "旋进运动", "旋轮线", "摆线")
    )

    if not has_electric:
        return 0.0, []

    score = 0.0
    evidence: list[str] = []
    if has_magnetic:
        score += 0.20
    if has_electric:
        score += 0.20
    if has_charged_body:
        score += 0.15
    if has_velocity_split:
        score += 0.25
        evidence.append(_evidence_snippet(text, "分解"))
    if has_balance:
        score += 0.15
        evidence.append(_evidence_snippet(text, "平衡"))
    if has_reference_drift:
        # Some classic solutions never say “速度分解”.  They construct the
        # qvB=qE reference motion and compare every particle with that drift;
        # this is the same structural method and should not be only “related”.
        score += 0.15
        evidence.append(_evidence_snippet(text, "恰好沿"))
    if has_superposition:
        score += 0.10
        for term in ("旋进运动", "匀速圆周运动", "匀速直线运动", "摆线"):
            if term in compact:
                evidence.append(_evidence_snippet(text, term))
                break
    if not has_balance or not (has_velocity_split or has_reference_drift or has_superposition):
        # Do not combine “速度分解” from one sub-question with force balance
        # from another.  A confirmed electric-method match needs both pieces in
        # the same local evidence window.
        score = min(score, 0.70)
    return min(score, 1.0), evidence


def _has_velocity_split(compact: str) -> bool:
    return (
        ("速度" in compact and "分解" in compact)
        or "分速度" in compact
        or ("取一个" in compact and "速度" in compact and "平衡" in compact)
        or ("选取" in compact and "速度" in compact and "平衡" in compact)
    )


def _has_mg_formula(text: str) -> bool:
    return bool(
        re.search(
            r"(?<![A-Za-z])m\s*(?:\\?[,;:]?\s*)g(?![A-Za-z])",
            text,
            flags=re.IGNORECASE,
        )
    )


def _has_qvb_equals_mg(text: str) -> bool:
    equation = _EQUATION_SPACE_RE.sub("", text).casefold()
    magnetic_term = r"(?:qv\d*b|b\d*qv\d*|bqv\d*|qbv\d*)"
    return bool(
        re.search(rf"{magnetic_term}=mg|mg={magnetic_term}", equation)
    )


def _has_qvb_equals_qe(text: str) -> bool:
    equation = _EQUATION_SPACE_RE.sub("", text).casefold()
    magnetic_term = r"(?:qv\d*b|b\d*qv\d*[′']*|bqv\d*[′']*|qbv\d*[′']*)"
    electric_term = r"(?:qe|eq)"
    return bool(
        re.search(
            rf"{magnetic_term}={electric_term}|{electric_term}={magnetic_term}",
            equation,
        )
    )


def _has_qe_formula(text: str) -> bool:
    return bool(
        re.search(
            r"(?<![A-Za-z])(?:q\s*(?:[_{}0-9]*)\s*E|E\s*q)(?![A-Za-z])",
            text,
            flags=re.IGNORECASE,
        )
    )


def _best_window_score(
    windows: list[str],
    scorer: Any,
) -> tuple[float, list[str]]:
    best_score = 0.0
    best_evidence: list[str] = []
    for text in windows:
        compact = _compact(text)
        formula_text = _FORMULA_SPACE_RE.sub("", text).casefold()
        score, evidence = scorer(text, compact, formula_text)
        if score > best_score:
            best_score = score
            best_evidence = evidence
    return best_score, best_evidence


_METHOD_SECTION_MARKER_RE = re.compile(
    r"(?=(?:【解析】|解法[一二三四五六\d]+\s*[:：]|第[一二三四五六\d]+问|[（(]\d+[）)]|[①-⑳⑴-⒇]))"
)


def _candidate_windows(row: dict[str, Any]) -> list[str]:
    title = " ".join(
        str(row.get(field) or "") for field in ("canonical_title", "title_text")
    ).strip()
    stem_segments = _split_method_segments(str(row.get("stem_text") or ""))
    analysis_segments = _split_method_segments(
        "\n".join(
            str(row.get(field) or "") for field in ("answer_text", "analysis_text")
        )
    )
    windows: list[str] = []
    for segments in (stem_segments, analysis_segments):
        windows.extend(segments)
    if stem_segments and analysis_segments:
        if len(stem_segments) == 1:
            windows.extend(
                f"{title}\n{stem_segments[0]}\n{analysis}"
                for analysis in analysis_segments
            )
        else:
            windows.extend(
                f"{title}\n{stem}\n{analysis_segments[min(index, len(analysis_segments) - 1)]}"
                for index, stem in enumerate(stem_segments)
            )
    elif stem_segments:
        windows.extend(f"{title}\n{stem}" for stem in stem_segments)
    elif analysis_segments:
        windows.extend(f"{title}\n{analysis}" for analysis in analysis_segments)
    return list(dict.fromkeys(window.strip() for window in windows if window.strip()))


def _split_method_segments(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = _METHOD_SECTION_MARKER_RE.sub("\x1e", normalized)
    return [
        segment.strip()
        for segment in normalized.split("\x1e")
        if segment.strip()
    ]


def _candidate_text(row: dict[str, Any]) -> str:
    return _candidate_body_text(row) + "\n" + _candidate_metadata_text(row)


def _candidate_body_text(row: dict[str, Any]) -> str:
    fields = (
        "canonical_title",
        "title_text",
        "stem_text",
        "answer_text",
        "analysis_text",
    )
    return "\n".join(str(row.get(field) or "") for field in fields)


def _candidate_metadata_text(row: dict[str, Any]) -> str:
    fields = (
        "module",
        "topic2",
        "topic3",
        "tags_json",
    )
    labels = " ".join(
        str(point.get("topic3_name") or "")
        for point in row.get("knowledge_points", [])
        if isinstance(point, dict)
    )
    return "\n".join(str(row.get(field) or "") for field in fields) + "\n" + labels


def _compact(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff/]+", "", str(text or "")).casefold()


def _evidence_snippet(text: str, term: str, radius: int = 90) -> str:
    position = text.find(term)
    if position < 0:
        return ""
    start = max(0, position - radius)
    end = min(len(text), position + len(term) + radius)
    return " ".join(text[start:end].split())
