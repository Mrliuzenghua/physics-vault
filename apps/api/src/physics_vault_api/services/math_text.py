"""Utilities for normalizing LaTeX delimiters in imported question text."""

from __future__ import annotations

import re

_DISPLAY_MATH = re.compile(r"\$\$([^\n]*?)\$\$")
_MIXED_MATH = re.compile(r"(?<!\$)\$([^\n$]{1,140}?)\$\$(?!\$)|(?<!\$)\$\$([^\n$]{1,140}?)\$(?!\$)")
_BLOCK_HINTS = ("\\begin", "\\end", "\\\\", "\\tag", "\\left.", "\\right.")


def normalize_short_inline_display_math(text: str) -> str:
    """Downgrade accidental inline display math spans to inline math.

    OCR, Pandoc, and LLM post-processing sometimes wrap short formulas inside a
    paragraph with display delimiters. Those render as separate equations in the
    review center, which makes ordinary stems hard to read. A display formula is
    kept when it occupies the whole line or looks like a real multi-line block.
    """

    normalized, _ = normalize_math_delimiters(text)
    return normalized


def normalize_math_delimiters(text: str) -> tuple[str, int]:
    """Normalize display/inline delimiters and report actual replacements."""

    if not text or "$$" not in text:
        return text, 0

    count = 0
    normalized_lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        normalized, line_count = _normalize_math_line(line)
        normalized_lines.append(normalized)
        count += line_count
    return "\n".join(normalized_lines), count


def normalize_question_math(question: dict) -> dict:
    """Return a copy of a question with short inline display math normalized."""

    normalized = dict(question)
    for field in ("title", "answer", "analysis", "raw_text"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = normalize_short_inline_display_math(value)

    options = normalized.get("options")
    if isinstance(options, list):
        normalized["options"] = [
            _normalize_option_math(option) if isinstance(option, dict) else option
            for option in options
        ]

    sub_questions = normalized.get("sub_questions")
    if isinstance(sub_questions, list):
        normalized["sub_questions"] = [
            normalize_question_math(item) if isinstance(item, dict) else item
            for item in sub_questions
        ]

    return normalized


def _normalize_option_math(option: dict) -> dict:
    normalized = dict(option)
    content = normalized.get("content")
    if isinstance(content, str):
        normalized["content"] = normalize_short_inline_display_math(content)
    return normalized


def _normalize_math_line(line: str) -> tuple[str, int]:
    stripped = line.strip()
    if not stripped:
        return line, 0

    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        replacement = _replace_math(line, match.group(0), match.group(1))
        if replacement != match.group(0):
            count += 1
        return replacement

    normalized = _DISPLAY_MATH.sub(replace, line)

    def repair(match: re.Match[str]) -> str:
        nonlocal count
        replacement = _replace_math(normalized, match.group(0), match.group(1) or match.group(2) or "")
        if replacement != match.group(0):
            count += 1
        return replacement

    return _MIXED_MATH.sub(repair, normalized), count


def _replace_math(line: str, full: str, formula: str) -> str:
    formula = formula.strip()
    if formula and line.strip() == full:
        return f"$${formula}$$"
    if not _should_downgrade(line, full, formula):
        return full
    return f"${formula}$"


def _should_downgrade(line: str, full: str, formula: str) -> bool:
    if not formula:
        return False
    if line.strip() == full:
        return False
    if len(formula) > 140:
        return False
    if any(hint in formula for hint in _BLOCK_HINTS):
        return False
    return True
