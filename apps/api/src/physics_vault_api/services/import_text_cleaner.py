"""Pure text-cleaning rules used by the document import pipeline."""

from __future__ import annotations

import re
from typing import Any

from .math_text import normalize_short_inline_display_math


class ImportTextCleaner:
    """Normalize extracted document text without touching files, tasks, or databases."""

    HEADER_PATTERNS = (
        re.compile(r"^\s*第\s*\d+\s*页\s*$"),
        re.compile(r"^\s*共\s*\d+\s*页\s*$"),
    )

    @classmethod
    def clean_text(
        cls,
        source_text: str,
        *,
        normalize_whitespace: bool,
        strip_headers_footers: bool,
        normalize_math_delimiters: bool,
        remove_blank_lines: bool,
    ) -> dict[str, str | int]:
        """Apply configurable, deterministic cleanup to extracted document text."""
        text = source_text.replace("\r\n", "\n").replace("\r", "\n")

        if normalize_math_delimiters:
            text = text.replace("\\(", "$").replace("\\)", "$")
            text = text.replace("\\[", "$$").replace("\\]", "$$")

        cleaned_lines: list[str] = []
        for line in text.split("\n"):
            candidate = re.sub(r"[ \t]+", " ", line).strip() if normalize_whitespace else line
            if strip_headers_footers and any(pattern.match(candidate) for pattern in cls.HEADER_PATTERNS):
                continue
            cleaned_lines.append(candidate)

        if remove_blank_lines:
            cleaned_lines = cls._compact_blank_lines(cleaned_lines)

        cleaned_text = normalize_short_inline_display_math("\n".join(cleaned_lines).strip())
        return {
            "cleaned_text": cleaned_text,
            "original_length": len(source_text),
            "cleaned_length": len(cleaned_text),
        }

    @classmethod
    def clean_markdown_for_import(cls, markdown: str, media_assets: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply import-safe Markdown cleanup while preserving image references and warnings."""
        text = markdown.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\\(", "$").replace("\\)", "$")
        text = text.replace("\\[", "$$").replace("\\]", "$$")

        media_refs = {
            str(asset.get("filename", "")).lower()
            for asset in media_assets
            if asset.get("filename")
        }

        cleaned_lines: list[str] = []
        warnings: list[str] = []
        for raw_line in text.split("\n"):
            line = re.sub(r"[ \t]+", " ", raw_line).strip()
            if re.fullmatch(r"(第\s*)?\d+\s*(页|/|／)?\s*(共\s*\d+\s*页)?", line):
                continue
            if re.fullmatch(r"[-=_]{3,}", line):
                continue
            if line.lower().startswith("![](") and media_refs and not any(name in line.lower() for name in media_refs):
                warnings.append(f"Unmatched image reference kept: {line[:80]}")
            cleaned_lines.append(line)

        cleaned_text = normalize_short_inline_display_math("\n".join(cls._compact_blank_lines(cleaned_lines)).strip())
        return {
            "cleaned_text": cleaned_text,
            "original_length": len(markdown),
            "cleaned_length": len(cleaned_text),
            "warnings": warnings,
        }

    @staticmethod
    def _compact_blank_lines(lines: list[str]) -> list[str]:
        compacted: list[str] = []
        last_blank = False
        for line in lines:
            is_blank = line == ""
            if is_blank and last_blank:
                continue
            compacted.append(line)
            last_blank = is_blank
        return compacted
