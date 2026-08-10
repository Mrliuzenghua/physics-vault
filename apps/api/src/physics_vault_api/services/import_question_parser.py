from __future__ import annotations

import re
from typing import Any

from ..schemas.import_pipeline import ParseStructuredQuestionsRequest
from .import_text_rules import extract_json_payload, normalize_ai_questions
from .math_text import normalize_question_math, normalize_short_inline_display_math
from .question_splitter import ExamQuestionSplitter


class ImportQuestionParser:
    """Parses local Markdown and AI text into reviewable question drafts."""

    QUESTION_SPLIT = re.compile(r"\n(?=(?:\d+[\.\u3001]\s*))")

    def __init__(self) -> None:
        self._splitter = ExamQuestionSplitter()

    def parse(self, payload: ParseStructuredQuestionsRequest) -> dict[str, Any]:
        chunks = [chunk.strip() for chunk in self.QUESTION_SPLIT.split(payload.source_text) if chunk.strip()]
        questions = [
            {
                "question_id": f"{payload.import_batch_id}-q{index:04d}",
                "question_type": "calculation",
                "title": chunk,
                "options": [],
                "answer": "",
                "analysis": "",
                "sub_questions": [],
                "figures": [],
                "difficulty": None,
                "knowledge_point": "",
                "tags": [],
                "source": payload.source_path or "",
                "import_batch_id": payload.import_batch_id,
            }
            for index, chunk in enumerate(chunks, start=1)
        ]
        return {"question_count": len(questions), "questions": questions}

    def parse_markdown_with_images(
        self,
        markdown: str,
        batch_id: str,
        source: str,
        media_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._splitter.split(
            markdown=markdown,
            batch_id=batch_id,
            source=source,
            media_assets=media_assets,
        )

    def parse_ai_generated_questions(self, source_text: str, batch_id: str, source: str) -> tuple[list[dict[str, Any]], list[str]]:
        return extract_generated_questions(source_text, batch_id, source)


class StructuredQuestionParsingService(ImportQuestionParser):
    """Backward-compatible name for the import question parser."""


def extract_generated_questions(source_text: str, batch_id: str, source: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    json_payload = extract_json_payload(source_text)
    if isinstance(json_payload, dict):
        questions = normalize_ai_questions(json_payload.get("questions") or [json_payload], batch_id, source)
        if questions:
            return questions, warnings
    if isinstance(json_payload, list):
        questions = normalize_ai_questions(json_payload, batch_id, source)
        if questions:
            return questions, warnings

    block_questions = parse_generated_question_blocks(source_text, batch_id, source)
    if block_questions:
        warnings.append("已按 AI 对话文本整理为待审核草稿，建议重点核对题干、答案和解析边界。")
        return block_questions, warnings

    split_result = ExamQuestionSplitter().split(source_text, batch_id=batch_id, source=source, media_assets=[])
    questions = split_result.get("questions") if isinstance(split_result, dict) else []
    if isinstance(questions, list) and questions:
        warnings.append("已按自然文本拆题，建议重点核对题干、答案和解析边界。")
        return questions, warnings

    fallback = fallback_single_generated_question(source_text, batch_id, source, 1)
    if fallback:
        warnings.append("未识别到明确题号，已将当前 AI 回复整理为 1 条待审核草稿。")
        return [fallback], warnings
    return [], ["没有识别到可送审的试题，请让 AI 按“题干、选项、答案、解析”重新输出。"]


def parse_generated_question_blocks(source_text: str, batch_id: str, source: str) -> list[dict[str, Any]]:
    text = source_text.strip()
    if not re.search(r"(答案|参考答案|解析|详解|分析|Answer|Ans\.?|Analysis|Solution|Explanation)\s*[：:]", text, flags=re.IGNORECASE):
        return []
    starts = list(re.finditer(r"(?m)^\s*(?:第\s*\d{1,3}\s*题\s*[：:]?|\d{1,3}\s*[\.、．]\s+)", text))
    if not starts:
        question = fallback_single_generated_question(text, batch_id, source, 1)
        return [question] if question else []

    questions: list[dict[str, Any]] = []
    for index, match in enumerate(starts, start=1):
        end = starts[index].start() if index < len(starts) else len(text)
        question = fallback_single_generated_question(text[match.start():end].strip(), batch_id, source, index)
        if question:
            questions.append(question)
    return questions


def fallback_single_generated_question(source_text: str, batch_id: str, source: str, index: int) -> dict[str, Any] | None:
    text = source_text.strip()
    if not text or not re.search(
        r"(题干|答案|解析|选项|Answer|Analysis|Solution|A[\.、．)]|B[\.、．)]|第\s*\d+\s*题)",
        text,
        flags=re.IGNORECASE,
    ):
        return None

    answer_match = re.search(
        r"(?:参考答案|答案|答|Answer|Ans\.?)\s*[：:]\s*([\s\S]*?)(?=(?:解析|详解|分析|Analysis|Solution|Explanation)\s*[：:]|$)",
        text,
        flags=re.IGNORECASE,
    )
    analysis_match = re.search(r"(?:解析|详解|分析|Analysis|Solution|Explanation)\s*[：:]\s*([\s\S]*)$", text, flags=re.IGNORECASE)
    stem_text = text[: answer_match.start()].strip() if answer_match else text
    stem_text = re.sub(r"^\s*(?:题干|试题|题目|Question|Stem)\s*[：:]\s*", "", stem_text, flags=re.IGNORECASE).strip()
    stem_text = re.sub(r"^\s*(?:第\s*\d{1,3}\s*题\s*[：:]?|\d{1,3}\s*[\.、．]\s*)", "", stem_text).strip()

    options: list[dict[str, Any]] = []
    stem_lines: list[str] = []
    for line in stem_text.splitlines():
        option_match = re.match(r"^\s*([A-H])\s*[\.、．)]\s*(.+)$", line)
        if option_match:
            options.append({"opt": option_match.group(1), "content": normalize_short_inline_display_math(option_match.group(2).strip())})
        else:
            stem_lines.append(line)

    stem = normalize_short_inline_display_math("\n".join(stem_lines).strip())
    if not stem:
        return None
    answer = normalize_short_inline_display_math(answer_match.group(1).strip()) if answer_match else ""
    analysis = normalize_short_inline_display_math(analysis_match.group(1).strip()) if analysis_match else ""
    return normalize_question_math(
        {
            "question_id": f"{batch_id}_q{index:04d}",
            "question_type": "single_choice" if options else "calculation",
            "title": stem,
            "options": options,
            "answer": answer,
            "analysis": analysis,
            "sub_questions": [],
            "figures": [],
            "difficulty": None,
            "knowledge_point": "",
            "tags": ["AI生成"],
            "source": source,
            "import_batch_id": batch_id,
            "raw_text": source_text,
            "confidence": 0.5,
        }
    )
