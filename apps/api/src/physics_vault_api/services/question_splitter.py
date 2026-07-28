"""Enhanced structural parser for exam-paper Markdown produced by Pandoc.

Splits a converted Word/markdown exam paper into structured questions:

- Recognises many question-number styles: ``1.`` ``1、`` ``1．`` ``1)`` ``（1）``
  ``【1】`` ``第1题`` (including Pandoc-escaped ``1\\.``).
- Extracts options (``A.`` ``A、`` ``A．`` ``A)`` ``（A）`` …), answer blocks
  (``【答案】`` ``答案：`` ``参考答案`` …) and analysis blocks
  (``【解析】`` ``解析：`` …).
- Replaces Markdown images with ``![fig:<uuid>]`` placeholders bound to the
  batch media manifest, so figure references survive later AI cleaning.
- Infers ``question_type`` from structure/content.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from .math_text import normalize_question_math

# ── Question-number detection (line start) ─────────────────────────

_QUESTION_START = re.compile(
    r"^\s*(?:>\s*)*(?:"
    r"(?:第\s*)?(\d{1,3})\s*\\?[\.、．] ?"   # 1.  1、  1．  1\. (pandoc)
    r"|(?:第\s*)(\d{1,3})\s*题\s*[:：.]?"      # 第1题  第1题:
    r"|[\(（【](\d{1,3})[\)）】]\s*"           # (1) （1） 【1】
    r")"
)

# Option line:  A. xxx   A、xxx   A．xxx   A) xxx   （A）xxx
# Pandoc sometimes wraps option paragraphs in blockquotes ("> A．…"),
# so an optional blockquote prefix is allowed.
_OPTION_LINE = re.compile(
    r"^\s*(?:>\s*)*[\(（【]?\s*([A-H])\s*\\?[\)）】\.、．]\s*(.*)$"
)

# Leading "A" marker — used to ENTER the options section
_FIRST_OPTION_LINE = re.compile(
    r"^\s*(?:>\s*)*[\(（【]?\s*A\s*\\?[\)）】\.、．]\s*\S"
)

# Inline multi-option on one line: "A. foo  B. bar  C. baz  D. qux"
_INLINE_OPTION_SPLIT = re.compile(
    r"[\(（【]?\s*([A-H])\s*\\?[\)）】\.、．]\s*"
)

# Answer / analysis section markers
_ANSWER_START = re.compile(
    r"^\s*[【\[]?\s*(参考答案|答案|解答|答)\s*[】\]]?\s*[:：]?\s*(.*)$"
)
_ANALYSIS_START = re.compile(
    r"^\s*[【\[]?\s*(解析|详解|分析|点拨|解答)\s*[】\]]?\s*[:：]?\s*(.*)$"
)

# Markdown image:  ![alt](path)  possibly followed by pandoc attrs {width=..}
_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)(?:\{[^}]*\})?")

# Stray pandoc attribute blocks left on their own line
_PANDOC_ATTR_LINE = re.compile(r"^\s*\{[^{}]*\}\s*$")

# Under-score / dash separator lines (sometimes used before answers)
_SEPARATOR_LINE = re.compile(r"^\s*[-=_]{3,}\s*$")

# ── Type inference keywords ────────────────────────────────────────

_EXPERIMENT_HINTS = ("实验", "探究", "测量", "用图甲装置", "打点计时器", "游标卡尺", "螺旋测微器")
_FILL_HINTS = ("填在", "填空", "填入", "应填", "结果为____", "为______")


def _infer_type(stem: str, options: list[dict], answer: str) -> str:
    if options:
        letters = re.findall(r"[A-H]", answer.strip())
        # Multiple distinct letters in the answer → multi choice
        if len(set(letters)) >= 2 and len(answer.strip()) <= 10:
            return "multi_choice"
        return "single_choice"
    if any(h in stem for h in _EXPERIMENT_HINTS):
        return "experiment"
    if any(h in stem for h in _FILL_HINTS):
        return "fill"
    return "calculation"


class ExamQuestionSplitter:
    """Split exam-paper Markdown into structured question dicts."""

    def split(
        self,
        markdown: str,
        batch_id: str,
        source: str,
        media_assets: list[dict],
    ) -> dict:
        text = markdown.replace("\r\n", "\n").replace("\r", "\n")
        # Normalize non-breaking spaces (common in Chinese exam papers) so
        # option/question markers and stems don't contain invisible \xa0.
        text = text.replace("\xa0", " ")
        lines = text.split("\n")

        chunks = self._split_chunks(lines)

        media_by_filename = {
            str(a["filename"]).replace("\\", "/").lower(): a for a in media_assets
        }
        media_by_path = {
            str(a["relative_path"]).replace("\\", "/").lower(): a for a in media_assets
        }

        questions: list[dict] = []
        for number, chunk_lines in chunks:
            figures: list[dict] = []

            def _replace_image(match: re.Match[str]) -> str:
                raw_ref = match.group(1).strip().strip('"')
                normalized = raw_ref.replace("\\", "/").lower()
                filename = Path(raw_ref).name.lower()
                asset = media_by_path.get(normalized) or media_by_filename.get(filename)
                if asset is None:
                    return ""
                fig_uuid = f"fig_{uuid4().hex[:12]}"
                figures.append(
                    {
                        "fig_uuid": fig_uuid,
                        "local_path": asset["relative_path"],
                        "role": "stem",
                        "confidence": 0.8,
                        "source_image_id": asset["image_id"],
                    }
                )
                return f"![fig:{fig_uuid}]"

            parsed = self._parse_chunk(chunk_lines)
            stem = _IMAGE_PATTERN.sub(_replace_image, parsed["stem"])
            # Clean leftover pandoc attr lines / stray separators inside stem
            stem_lines = [
                ln for ln in stem.split("\n")
                if not _PANDOC_ATTR_LINE.match(ln)
            ]
            stem = "\n".join(stem_lines).strip()

            # Image substitution applies to options/answer/analysis as well —
            # choice questions can have image-only options (e.g. circuit diagrams).
            options = [
                {"opt": o["opt"], "content": _IMAGE_PATTERN.sub(_replace_image, o["content"])}
                for o in parsed["options"]
            ]
            answer = _IMAGE_PATTERN.sub(_replace_image, parsed["answer"]).strip()
            analysis = _IMAGE_PATTERN.sub(_replace_image, parsed["analysis"]).strip()
            q_type = _infer_type(stem, options, answer)

            idx = len(questions) + 1
            questions.append(
                normalize_question_math({
                    "question_id": f"{batch_id}_q{idx:04d}",
                    "question_no": number,
                    "question_type": q_type,
                    "title": stem,
                    "options": options,
                    "answer": answer,
                    "analysis": analysis,
                    "sub_questions": [],
                    "figures": figures,
                    "difficulty": 0,
                    "knowledge_point": "",
                    "tags": [],
                    "source": source,
                    "import_batch_id": batch_id,
                    "confidence": 0.6,
                })
            )

        return {"question_count": len(questions), "questions": questions}

    # ── Stage 1: split whole text into (number, lines) chunks ──────

    def _split_chunks(self, lines: list[str]) -> list[tuple[int, list[str]]]:
        # ── Pass 1: decide which question-number family this paper uses ──
        # Sub-questions almost always use the (1)(2)(3) bracket style, so
        # bracket-style starts are only trusted when no plain/第N题 style
        # question numbers exist anywhere in the document.
        plain_hits = 0
        bracket_hits = 0
        for line in lines:
            m = _QUESTION_START.match(line)
            if not m:
                continue
            if m.group(3) is not None:
                bracket_hits += 1
            else:
                plain_hits += 1
        use_bracket = plain_hits == 0 and bracket_hits > 0

        chunks: list[tuple[int, list[str]]] = []
        preamble: list[str] = []
        current: list[str] = []
        current_no = 0
        seen_first = False
        prev_no = 0

        for line in lines:
            m = _QUESTION_START.match(line)
            if m:
                is_bracket = m.group(3) is not None
                if is_bracket and not use_bracket:
                    m = None  # sub-question style — not a real question start
            if m:
                no = int(next(g for g in m.groups() if g is not None))
                # Heuristic: question numbers should increase
                is_sequence = seen_first and no > prev_no
                is_first = not seen_first
                if is_first or is_sequence:
                    if current:
                        chunks.append((current_no, current))
                    elif not seen_first:
                        preamble = []
                    current = [line]
                    current_no = no
                    prev_no = no
                    seen_first = True
                    continue
            if not seen_first:
                preamble.append(line)
            else:
                current.append(line)

        if current:
            chunks.append((current_no, current))

        # If no question numbers were detected at all, treat whole doc as one chunk
        if not seen_first and chunks:
            return [(1, chunks[0][1])]
        return chunks

    # ── Stage 2: parse one chunk into stem/options/answer/analysis ─

    def _parse_chunk(self, lines: list[str]) -> dict:
        # First line still carries the question number — strip it
        first = lines[0] if lines else ""
        m = _QUESTION_START.match(first)
        if m:
            first = first[m.end():].lstrip()
        body_lines = [first] + lines[1:]

        # Normalize: strip pandoc HTML comments and blockquote markers.
        # Blockquotes in pandoc output are formatting artifacts (the docx
        # paragraph was indented), not semantic quotes.
        normalized: list[str] = []
        for ln in body_lines:
            if ln.strip().startswith("<!--"):
                continue
            stripped = ln
            s = stripped.lstrip()
            while s.startswith(">"):
                s = s[1:].lstrip()
            normalized.append(s)
        body_lines = normalized

        stem_parts: list[str] = []
        options: list[dict] = []
        answer_parts: list[str] = []
        analysis_parts: list[str] = []

        section = "stem"  # stem → options → answer/analysis
        option_buffer: list[str] = []

        def flush_option_buffer() -> None:
            nonlocal option_buffer
            if not option_buffer:
                return
            # Strip blockquote markers and drop bare ">" lines before joining
            cleaned = []
            for ln in option_buffer:
                stripped = ln.strip()
                while stripped.startswith(">"):
                    stripped = stripped[1:].strip()
                if stripped:
                    cleaned.append(stripped)
            joined = " ".join(cleaned)
            option_buffer = []
            for letter, content in self._split_options_text(joined):
                options.append({"opt": letter, "content": content})

        for raw in body_lines:
            line = raw.rstrip()

            answer_m = _ANSWER_START.match(line)
            analysis_m = _ANALYSIS_START.match(line)
            if answer_m and section != "analysis":
                flush_option_buffer()
                section = "answer"
                inline = answer_m.group(2).strip()
                if inline:
                    answer_parts.append(inline)
                continue
            if analysis_m:
                flush_option_buffer()
                section = "analysis"
                inline = analysis_m.group(2).strip()
                if inline:
                    analysis_parts.append(inline)
                continue

            if _SEPARATOR_LINE.match(line):
                continue

            if section == "stem":
                # Enter options only on a clear leading "A."-style marker
                if _FIRST_OPTION_LINE.match(line):
                    section = "options"
                    option_buffer.append(line)
                    continue
                stem_parts.append(line)
                continue

            if section == "options":
                # Buffer everything until an answer/analysis marker — pandoc
                # hard-wraps options mid-line, so we re-join before splitting.
                option_buffer.append(line)
                continue

            target = answer_parts if section == "answer" else analysis_parts
            target.append(line)

        flush_option_buffer()

        return {
            "stem": "\n".join(stem_parts).strip(),
            "options": options,
            "answer": "\n".join(answer_parts),
            "analysis": "\n".join(analysis_parts),
        }

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _split_options_text(text: str) -> list[tuple[str, str]]:
        """Split a joined options string into [(letter, content), ...].

        Handles ``A. foo B. bar`` / ``A、foo B、bar`` / ``(A) foo (B) bar``.
        """
        matches = list(_INLINE_OPTION_SPLIT.finditer(text))
        if not matches:
            return []
        # First marker must be at (or very near) the start and letters must
        # be consecutive from A.
        if matches[0].start() > 3:
            return []
        letters = [m.group(1) for m in matches]
        if letters[0] != "A":
            return []
        if letters != [chr(ord("A") + i) for i in range(len(letters))]:
            return []
        result: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            result.append((m.group(1), text[m.end():end].strip()))
        return result
