"""Rule-based similar-question search.

Scoring is purely deterministic, using only the structured fields already
present in the database.  No embedding, no vector, no external service.
"""

from __future__ import annotations

import logging
from typing import Any

from ..repositories.question_search import QuestionSearchRepository
from ..schemas.similar_questions import SimilarQuestionItem, SimilarQuestionsResponse

logger = logging.getLogger(__name__)

# ── Scoring weights (all additive; total ≤ 100 after normalisation) ──

WEIGHT_SAME_QUESTION_TYPE = 30
WEIGHT_SAME_TOPIC3 = 35
WEIGHT_SAME_TOPIC2 = 20
WEIGHT_SAME_MODULE = 10
WEIGHT_DIFFICULTY_EXACT = 15
WEIGHT_DIFFICULTY_NEAR = 8
WEIGHT_TAG_OVERLAP_PER_TAG = 5
WEIGHT_KEYWORD_OVERLAP_PER_WORD = 3  # capped
WEIGHT_HAS_MEDIA_MATCH = 5

MAX_KEYWORD_SCORE = 15
MAX_TAG_SCORE = 15


class SimilarQuestionsService:
    """Finds questions similar to a given source question using rule-based scoring."""

    def __init__(self, repository: QuestionSearchRepository | None = None) -> None:
        self._repo = repository or QuestionSearchRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_similar(
        self,
        question_id: str,
        limit: int = 10,
        same_question_type: bool = False,
        same_knowledge_point: bool = False,
        difficulty_tolerance: int = 99,
    ) -> SimilarQuestionsResponse:
        """Return questions similar to *question_id*."""

        # 1. Fetch the source question
        source = self._get_question(question_id)
        if source is None:
            return SimilarQuestionsResponse(
                question_id=question_id, items=[], total_candidates=0, limit=limit
            )

        # 2. Fetch candidates (broad: all questions except self, optionally filtered)
        candidates = self._fetch_candidates(
            source,
            same_question_type=same_question_type,
            same_knowledge_point=same_knowledge_point,
        )

        # 3. Score every candidate
        scored: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates:
            if candidate["question_id"] == question_id:
                continue
            score = self._score(source, candidate, difficulty_tolerance)
            if score > 0:
                scored.append((score, candidate))

        # 4. Sort by score descending, then by difficulty proximity, then by question_id
        def _sort_key(item: tuple[float, dict[str, Any]]) -> tuple[float, float, str]:
            score, c = item
            diff_gap = abs(
                int(source.get("difficulty", 3) or 3) - int(c.get("difficulty", 3) or 3)
            )
            return (-score, diff_gap, c.get("question_id", ""))

        scored.sort(key=_sort_key)

        # 5. Limit
        top = scored[:limit]

        items = [
            SimilarQuestionItem(
                question_id=c["question_id"],
                question_type=c.get("question_type"),
                title=c.get("canonical_title") or c.get("title"),
                difficulty=str(c.get("difficulty", "")),
                module=c.get("module"),
                topic2=c.get("topic2"),
                topic3=c.get("topic3"),
                similarity_score=round(score, 1),
                has_media=bool(c.get("has_media", False)),
                primary_paper_id=c.get("primary_paper_id"),
            )
            for score, c in top
        ]

        return SimilarQuestionsResponse(
            question_id=question_id,
            items=items,
            total_candidates=len(candidates),
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Scoring engine
    # ------------------------------------------------------------------

    def _score(
        self,
        source: dict[str, Any],
        candidate: dict[str, Any],
        difficulty_tolerance: int,
    ) -> float:
        score = 0.0

        # — same question type —
        src_type = str(source.get("question_type", "")).strip()
        cand_type = str(candidate.get("question_type", "")).strip()
        if src_type and cand_type and src_type == cand_type:
            score += WEIGHT_SAME_QUESTION_TYPE

        # — same topic3 (most specific) —
        src_t3 = str(source.get("topic3", "")).strip()
        cand_t3 = str(candidate.get("topic3", "")).strip()
        if src_t3 and cand_t3 and src_t3 == cand_t3:
            score += WEIGHT_SAME_TOPIC3

        # — same topic2 —
        src_t2 = str(source.get("topic2", "")).strip()
        cand_t2 = str(candidate.get("topic2", "")).strip()
        if src_t2 and cand_t2 and src_t2 == cand_t2:
            score += WEIGHT_SAME_TOPIC2

        # — same module —
        src_mod = str(source.get("module", "")).strip()
        cand_mod = str(candidate.get("module", "")).strip()
        if src_mod and cand_mod and src_mod == cand_mod:
            score += WEIGHT_SAME_MODULE

        # — difficulty proximity —
        src_diff = self._safe_int(source.get("difficulty"))
        cand_diff = self._safe_int(candidate.get("difficulty"))
        if src_diff is not None and cand_diff is not None:
            gap = abs(src_diff - cand_diff)
            if gap == 0:
                score += WEIGHT_DIFFICULTY_EXACT
            elif gap <= difficulty_tolerance:
                score += WEIGHT_DIFFICULTY_NEAR

        # — tag overlap —
        src_tags = set(self._normalize_tags(source.get("tags", [])))
        cand_tags = set(self._normalize_tags(candidate.get("tags", [])))
        overlap = len(src_tags & cand_tags)
        score += min(overlap * WEIGHT_TAG_OVERLAP_PER_TAG, MAX_TAG_SCORE)

        # — keyword overlap in title —
        src_title = str(source.get("canonical_title", "") or source.get("title", ""))
        cand_title = str(candidate.get("canonical_title", "") or candidate.get("title", ""))
        if src_title and cand_title:
            src_words = set(self._tokenize(src_title))
            cand_words = set(self._tokenize(cand_title))
            word_overlap = len(src_words & cand_words)
            score += min(word_overlap * WEIGHT_KEYWORD_OVERLAP_PER_WORD, MAX_KEYWORD_SCORE)

        # — has_media match —
        src_media = bool(source.get("has_media", False))
        cand_media = bool(candidate.get("has_media", False))
        if src_media == cand_media:
            score += WEIGHT_HAS_MEDIA_MATCH

        return score

    # ------------------------------------------------------------------
    # Data access helpers
    # ------------------------------------------------------------------

    def _get_question(self, question_id: str) -> dict[str, Any] | None:
        """Fetch a single question by ID."""
        rows = self._repo.get_questions_by_ids([question_id])
        return rows[0] if rows else None

    def _fetch_candidates(
        self,
        source: dict[str, Any],
        same_question_type: bool,
        same_knowledge_point: bool,
    ) -> list[dict[str, Any]]:
        """Fetch a broad candidate pool, optionally pre-filtered by type/topic."""
        qt = str(source.get("question_type", "")) if same_question_type else None
        t3 = str(source.get("topic3", "")) if same_knowledge_point else None
        t2 = str(source.get("topic2", "")) if same_knowledge_point else None

        rows, _ = self._repo.search_questions(
            search_mode="browse",
            question_type=qt,
            topic3=t3,
            topic2=t2,
            limit=200,
            offset=0,
        )
        return list(rows)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_tags(tags: Any) -> list[str]:
        if isinstance(tags, list):
            return [str(t).strip().lower() for t in tags if t]
        if isinstance(tags, str):
            try:
                import json
                parsed = json.loads(tags)
                if isinstance(parsed, list):
                    return [str(t).strip().lower() for t in parsed if t]
            except (json.JSONDecodeError, TypeError):
                pass
            return [tags.strip().lower()]
        return []

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple Chinese-aware tokenizer — splits on common delimiters and
        extracts 2-char bigrams as well as whole-character sequences."""
        import re

        cleaned = re.sub(r"[^一-鿿\w]", " ", text)
        tokens = [t for t in cleaned.split() if len(t) >= 1]
        # Add bigrams for Chinese text
        bigrams: list[str] = []
        for token in tokens:
            if len(token) >= 2:
                bigrams.extend(token[i : i + 2] for i in range(len(token) - 1))
        return tokens + bigrams
