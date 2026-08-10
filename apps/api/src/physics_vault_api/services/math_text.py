"""Utilities for normalizing LaTeX delimiters in imported question text."""

from __future__ import annotations

import re

_DISPLAY_MATH = re.compile(r"\$\$([^\n]*?)\$\$")
_MIXED_MATH = re.compile(r"(?<!\$)\$([^\n$]{1,140}?)\$\$(?!\$)|(?<!\$)\$\$([^\n$]{1,140}?)\$(?!\$)")
_BLOCK_HINTS = ("\\begin", "\\end", "\\\\", "\\tag", "\\left.", "\\right.")
_MATH_TOKEN = re.compile(r"\$\$[\s\S]*?\$\$|\$[^\n$]+?\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]")
_CHINESE_SUBSCRIPT = re.compile(r"([A-Za-z])_\{([\u3400-\u9fff\uF900-\uFAFF]+)\}")


def normalize_short_inline_display_math(text: str) -> str:
    """Downgrade accidental inline display math spans to inline math.

    OCR, Pandoc, and LLM post-processing sometimes wrap short formulas inside a
    paragraph with display delimiters. Those render as separate equations in the
    review center, which makes ordinary stems hard to read. A display formula is
    kept when it occupies the whole line or looks like a real multi-line block.
    """

    normalized, _ = normalize_math_delimiters(text)
    return normalized


def normalize_standard_latex(text: str) -> str:
    """Repair common imported fragments into stored, standard LaTeX.

    This deliberately handles only unambiguous fragments. Existing math spans
    are preserved while Chinese subscripts are written as ``\\text{...}``.
    """
    if not text or not any(marker in text for marker in ("_", "^", "\\")):
        return text

    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    plain = _MATH_TOKEN.sub(protect, text)
    plain = re.sub(
        r"(?<![A-Za-z0-9])[A-Za-z](?:_\{[^{}\n]{1,20}\}|_\w+)(?:\^\{[^{}\n]{1,20}\}|\^\w+)?",
        lambda match: f"${match.group(0)}$",
        plain,
    )
    plain = re.sub(
        r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*\\text\{[^{}\n]{1,20}\}(?:\^\{[^{}\n]{1,20}\}|\^\w+)?",
        lambda match: f"${match.group(0)}$",
        plain,
    )
    plain = _CHINESE_SUBSCRIPT.sub(r"\1_{\\text{\2}}", plain)

    def standardize_math(value: str) -> str:
        return _CHINESE_SUBSCRIPT.sub(r"\1_{\\text{\2}}", value)

    normalized = plain.replace("\x00", "\x00")
    for index, value in enumerate(protected):
        normalized = normalized.replace(f"\x00{index}\x00", standardize_math(value))
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


def repair_unbalanced_inline_math(text: str) -> tuple[str, int]:
    """Repair common OCR/LLM omissions in single-dollar inline math."""

    if not text or "$" not in text:
        return text, 0

    output: list[str] = []
    in_math = False
    brace_depth = 0
    replacements = 0
    index = 0

    while index < len(text):
        character = text[index]

        if character == "\\" and index + 1 < len(text):
            output.append(text[index : index + 2])
            index += 2
            continue

        if text.startswith("$$", index):
            output.append("$$")
            index += 2
            continue

        if character == "$":
            if not in_math:
                lookahead = index + 1
                while lookahead < len(text) and text[lookahead].isspace():
                    lookahead += 1
                if lookahead < len(text) and _looks_like_stray_math_open(text, lookahead):
                    replacements += 1
                    index += 1
                    continue
                in_math = True
                brace_depth = 0
            else:
                in_math = False
                brace_depth = 0
            output.append(character)
            index += 1
            continue

        if in_math:
            if character == "{":
                brace_depth += 1
            elif character == "}" and brace_depth:
                brace_depth -= 1

            if brace_depth == 0 and _is_math_text_boundary(text, index):
                output.append("$")
                replacements += 1
                in_math = False
                brace_depth = 0

        output.append(character)
        index += 1

    if in_math:
        output.append("$")
        replacements += 1

    return "".join(output), replacements


def _looks_like_stray_math_open(text: str, index: int) -> bool:
    character = text[index]
    if _is_cjk(character):
        return True
    if character in "（([【":
        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        return next_index < len(text) and _is_cjk(text[next_index])
    return False


def _is_math_text_boundary(text: str, index: int) -> bool:
    character = text[index]
    if character == "\n" or _is_cjk(character):
        return True
    if character in "，。；：、,;:" and _next_non_space_is_cjk(text, index + 1):
        return True
    at_line_start = index == 0 or text[index - 1] == "\n"
    if at_line_start and (text.startswith("![", index) or text.startswith("> ", index)):
        return True
    return False


def _next_non_space_is_cjk(text: str, index: int) -> bool:
    while index < len(text) and text[index].isspace():
        index += 1
    return index < len(text) and _is_cjk(text[index])


def _is_cjk(character: str) -> bool:
    return "\u3400" <= character <= "\u9fff" or "\uF900" <= character <= "\uFAFF"


def normalize_question_math(question: dict) -> dict:
    """Return a copy of a question with short inline display math normalized."""

    normalized = dict(question)
    for field in ("title", "answer", "analysis", "raw_text"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = normalize_standard_latex(normalize_short_inline_display_math(value))

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
        normalized["content"] = normalize_standard_latex(normalize_short_inline_display_math(content))
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
