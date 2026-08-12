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

# Pandoc can place a floating Word image before the question number that was
# visually beside it.  Attributes may wrap onto a second line, for example:
#
#   ![](image.png){width="2in"
#   height="1in"}1. Question text
#
# Move only an immediately-adjacent question marker in front of the image so
# the regular line-start parser can see it.  Deliberately do not cross blank
# space after the image: an image at the end of one question must stay there.
_IMAGE_PREFIXED_QUESTION = re.compile(
    r"(?P<image>!\[[^\]]*\]\([^)]+\)(?:\{[^}]*\})?)"
    r"(?P<marker>\d{1,3}\s*\\?[\.\u3001\uff0e][ \t]*)"
)

# Numbered exam instructions frequently look exactly like questions.  A real
# section heading is a much stronger boundary, so ignore everything before the
# first recognized exam section when one is present.
_SECTION_HEADING = re.compile(
    r"^\s*(?:>\s*)*(?:#{1,6}\s*)*(?:\*\*|__)?\s*"
    r"(?:第\s*[一二三四五六七八九十\d]+\s*(?:部分|大题)|[一二三四五六七八九十]+)"
    r"\s*[、\.．:：]\s*"
    r"(?:单项选择题|单选题|多项选择题|多选题|选择题|非选择题|填空题|实验题|计算题|解答题)",
)

# Stray pandoc attribute blocks left on their own line
_PANDOC_ATTR_LINE = re.compile(r"^\s*\{[^{}]*\}\s*$")

# Under-score / dash separator lines (sometimes used before answers)
_SEPARATOR_LINE = re.compile(r"^\s*[-=_]{3,}\s*$")

# ── Type inference keywords ────────────────────────────────────────

_EXPERIMENT_HINTS = ("实验", "探究", "测量", "用图甲装置", "打点计时器", "游标卡尺", "螺旋测微器")
_FILL_HINTS = ("填在", "填空", "填入", "应填", "结果为____", "为______")


def is_clearly_experiment_question(stem: str) -> bool:
    """Recognize experiment structure without relying on one broad keyword."""
    text = re.sub(r"!\[fig:[^\]]+\]", " ", str(stem or ""))
    strong_phrase = re.search(
        r"在.{0,24}(?:实验|探究)中|实验(?:步骤|装置|器材|数据|原理)|"
        r"测绘.{0,20}特性曲线|连接.{0,16}电路|完成.{0,16}实验",
        text,
    )
    steps = re.findall(r"[①②③④⑤⑥⑦⑧⑨⑩]|(?:^|\n)\s*[（(]\d+[)）]", text)
    return bool(strong_phrase and (len(steps) >= 2 or re.search(r"实验(?:中|步骤|装置|器材|数据|原理)", text)))


def _infer_type(stem: str, options: list[dict], answer: str, section_hint: str | None = None) -> str:
    experiment_text = "\n".join([stem, *(str(option.get("content") or "") for option in options)])
    if section_hint == "single_choice":
        return "single_choice"
    if section_hint == "multi_choice":
        return "multi_choice"
    if section_hint == "experiment":
        return "experiment"
    if section_hint == "fill":
        return "fill"
    if section_hint == "calculation":
        return "calculation"
    if section_hint == "non_choice":
        if is_clearly_experiment_question(experiment_text) or re.search(
            r"实验小组|实验器材|实验操作|验证.{0,16}(?:定律|规律|关系)|"
            r"探究.{0,16}(?:特性|规律|关系)",
            experiment_text,
        ):
            return "experiment"
        if any(h in stem for h in _FILL_HINTS):
            return "fill"
        return "calculation"
    if is_clearly_experiment_question(experiment_text):
        return "experiment"
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
        text = _IMAGE_PREFIXED_QUESTION.sub(
            lambda match: f"{match.group('marker')}{match.group('image')}",
            text,
        )
        lines = text.split("\n")

        chunks = self._split_chunks(lines)

        media_by_filename = {
            str(a["filename"]).replace("\\", "/").lower(): a for a in media_assets
        }
        media_by_path = {
            str(a["relative_path"]).replace("\\", "/").lower(): a for a in media_assets
        }

        questions: list[dict] = []
        for number, chunk_lines, section_hint in chunks:
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

            parsed = self._parse_chunk(chunk_lines, section_hint=section_hint)
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
            q_type = _infer_type(stem, options, answer, section_hint=section_hint)

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

    def _split_chunks(self, lines: list[str]) -> list[tuple[int, list[str], str | None]]:
        first_section_index = next(
            (index for index, line in enumerate(lines) if _SECTION_HEADING.match(line)),
            None,
        )
        scan_lines = lines[first_section_index:] if first_section_index is not None else lines

        # ── Pass 1: decide which question-number family this paper uses ──
        # Sub-questions almost always use the (1)(2)(3) bracket style, so
        # bracket-style starts are only trusted when no plain/第N题 style
        # question numbers exist anywhere in the document.
        plain_hits = 0
        bracket_hits = 0
        for line in scan_lines:
            if _SECTION_HEADING.match(line):
                continue
            m = _QUESTION_START.match(line)
            if not m:
                continue
            if m.group(3) is not None:
                bracket_hits += 1
            else:
                plain_hits += 1
        use_bracket = plain_hits == 0 and bracket_hits > 0

        chunks: list[tuple[int, list[str], str | None]] = []
        preamble: list[str] = []
        current: list[str] = []
        current_no = 0
        current_section_hint: str | None = None
        active_section_hint: str | None = None
        seen_first = False
        prev_no = 0

        for line in scan_lines:
            if _SECTION_HEADING.match(line):
                active_section_hint = self._section_hint(line)
                continue
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
                        chunks.append((current_no, current, current_section_hint))
                    elif not seen_first:
                        preamble = []
                    current = [line]
                    current_no = no
                    current_section_hint = active_section_hint
                    prev_no = no
                    seen_first = True
                    continue
            if not seen_first:
                preamble.append(line)
            else:
                current.append(line)

        if current:
            chunks.append((current_no, current, current_section_hint))

        # If no question numbers were detected at all, treat whole doc as one chunk
        if not seen_first and chunks:
            return [(1, chunks[0][1], chunks[0][2])]
        return chunks

    @staticmethod
    def _section_hint(line: str) -> str | None:
        if "单项选择" in line or "单选题" in line:
            return "single_choice"
        if "多项选择" in line or "多选题" in line:
            return "multi_choice"
        if "非选择题" in line:
            return "non_choice"
        if "实验题" in line:
            return "experiment"
        if "填空题" in line:
            return "fill"
        if "计算题" in line or "解答题" in line:
            return "calculation"
        if "选择题" in line:
            return "single_choice"
        return None

    # ── Stage 2: parse one chunk into stem/options/answer/analysis ─

    def _parse_chunk(self, lines: list[str], section_hint: str | None = None) -> dict:
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

        for line_index, raw in enumerate(body_lines):
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
                option_match = _OPTION_LINE.match(line)
                next_nonempty = next(
                    (candidate.strip() for candidate in body_lines[line_index + 1 :] if candidate.strip()),
                    "",
                )
                starts_image_options = bool(
                    option_match
                    and option_match.group(1) == "A"
                    and not option_match.group(2).strip()
                    and next_nonempty.startswith("![")
                )
                if section_hint != "non_choice" and (
                    _FIRST_OPTION_LINE.match(line) or starts_image_options
                ):
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

        stem = "\n".join(stem_parts).strip()
        if not options and section_hint in {"single_choice", "multi_choice"}:
            stem, options = self._extract_trailing_inline_options(stem)

        return {
            "stem": stem,
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

    @classmethod
    def _extract_trailing_inline_options(cls, text: str) -> tuple[str, list[dict[str, str]]]:
        """Extract a complete A-D run that Pandoc left at the end of the stem.

        Floating images often make the first option start midway through a
        Markdown line (``![...](figure)A. ...``).  Four consecutive markers
        are required to avoid mistaking physics point labels for options.
        """
        matches = list(_INLINE_OPTION_SPLIT.finditer(text))
        expected = ["A", "B", "C", "D"]
        for index in range(max(0, len(matches) - 3)):
            candidate_matches = matches[index : index + 4]
            if [match.group(1) for match in candidate_matches] != expected:
                continue
            option_text = text[candidate_matches[0].start() :]
            parsed = cls._split_options_text(option_text)
            if len(parsed) != 4:
                continue
            return (
                text[: candidate_matches[0].start()].rstrip(),
                [{"opt": letter, "content": content} for letter, content in parsed],
            )
        return text, []
