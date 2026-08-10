"""Stable, conservative content fingerprints for canonical questions."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def normalize_question_value(value: Any) -> str:
    """Ignore whitespace, punctuation and OCR-formatting noise for exact matching."""
    return re.sub(r"[\s\W_]+", "", str(value or ""), flags=re.UNICODE).casefold()


def normalize_question_options(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return normalize_question_value(value)
    if not isinstance(value, list):
        return ""
    normalized: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = item.get("label", item.get("opt", ""))
            text = item.get("text", item.get("content", ""))
            normalized.append(f"{normalize_question_value(label)}:{normalize_question_value(text)}")
        else:
            normalized.append(normalize_question_value(item))
    return "|".join(normalized)


def canonical_question_fingerprint(
    *,
    question_type: Any,
    title: Any,
    stem: Any,
    options: Any,
    answer: Any,
) -> str | None:
    """Return a hash only when enough decisive content is available.

    Analysis and source are deliberately excluded: the same question may have a
    corrected explanation or come from multiple papers, while still being one
    canonical question.
    """
    normalized_title = normalize_question_value(title)
    normalized_stem = normalize_question_value(stem)
    normalized_answer = normalize_question_value(answer)
    normalized_options = normalize_question_options(options)
    if len(normalized_title + normalized_stem) < 16 or not normalized_answer:
        return None
    payload = "\x1f".join(
        (
            normalize_question_value(question_type),
            normalized_title,
            normalized_stem,
            normalized_options,
            normalized_answer,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
