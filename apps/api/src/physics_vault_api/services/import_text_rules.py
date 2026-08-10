from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .math_text import normalize_question_math, normalize_short_inline_display_math
from .question_splitter import is_clearly_experiment_question


_ANSWER_DIFFICULTY_RE = re.compile(r"【\s*难度\s*】\s*([01](?:\.\d+)?)", re.IGNORECASE)
_ANSWER_KNOWLEDGE_RE = re.compile(r"【\s*知识点\s*】\s*([^【\r\n]+)", re.IGNORECASE)
_MULTI_CHOICE_ANSWER_RE = re.compile(r"^[A-H]{2,}$")
_PROVINCES = (
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "全国",
)


def normalize_source_name(value: Any) -> str:
    source = " ".join(str(value or "").split()).strip()
    if not source or "·" in source:
        return source
    year_match = re.search(r"(20\d{2})", source)
    province = next((item for item in _PROVINCES if item in source), "")
    if not year_match or not province or "高考" not in source:
        return source
    suffix = ""
    option_match = re.search(r"([（(]?\s*\d{1,2}\s*月选考\s*[)）]?)", source)
    if option_match:
        suffix = f"（{re.sub(r'[^0-9月选考]', '', option_match.group(1))}）"
    return f"{year_match.group(1)}年高考·{province}卷·物理{suffix}"


def difficulty_level(score: float) -> int:
    if score >= 0.85:
        return 2
    if score >= 0.65:
        return 3
    if score >= 0.40:
        return 4
    return 5


def normalize_import_question_metadata(question: dict[str, Any]) -> dict[str, Any]:
    """Normalize import metadata without changing substantive question content."""
    normalized = dict(question)
    warnings = [str(item) for item in normalized.get("validation_warnings") or [] if str(item).strip()]
    answer = str(normalized.get("answer") or "").strip()
    difficulty_match = _ANSWER_DIFFICULTY_RE.search(answer)
    knowledge_match = _ANSWER_KNOWLEDGE_RE.search(answer)
    if difficulty_match:
        normalized["difficulty"] = difficulty_level(float(difficulty_match.group(1)))
        answer = _ANSWER_DIFFICULTY_RE.sub("", answer)
        warnings.append("已从答案中提取难度元数据。")
    if knowledge_match:
        knowledge = knowledge_match.group(1).strip(" ，,;；。")
        if knowledge and not str(normalized.get("knowledge_point") or "").strip():
            normalized["knowledge_point"] = knowledge
        answer = _ANSWER_KNOWLEDGE_RE.sub("", answer)
        warnings.append("已从答案中提取知识点元数据。")
    answer = re.sub(r"\s{2,}", " ", answer).strip(" \t\r\n,，;；")
    normalized["answer"] = answer

    question_type = str(normalized.get("question_type") or "calculation").strip()
    compact_answer = re.sub(r"[^A-H]", "", answer.upper())
    experiment_text = "\n".join([
        str(normalized.get("title") or ""),
        *(str(option.get("content") or "") for option in normalized.get("options") or [] if isinstance(option, dict)),
    ])
    if question_type in {"single_choice", "multi_choice"} and is_clearly_experiment_question(experiment_text):
        normalized["question_type"] = "experiment"
        warnings.append("题干具有明确的多步骤实验结构，题型已修正为实验题。")
    elif question_type == "single_choice" and _MULTI_CHOICE_ANSWER_RE.fullmatch(compact_answer):
        normalized["question_type"] = "multi_choice"
        warnings.append("答案包含多个选项，题型已从单选修正为多选。")

    original_source = str(normalized.get("source_raw") or normalized.get("source") or "").strip()
    source = normalize_source_name(normalized.get("source"))
    if original_source:
        normalized["source_raw"] = original_source
    if source:
        normalized["source"] = source
    if warnings:
        normalized["validation_warnings"] = list(dict.fromkeys(warnings))
    return normalized


def source_extension(metadata: dict[str, Any]) -> str:
    return Path(str(metadata.get("stored_filename") or metadata.get("original_filename") or "")).suffix.lower().lstrip(".")


def normalize_ai_questions(raw_questions: Any, batch_id: str, source: str) -> list[dict[str, Any]]:
    questions = raw_questions if isinstance(raw_questions, list) else []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            normalize_import_question_metadata({
                "question_id": str(item.get("question_id") or f"{batch_id}-q{index:04d}"),
                "question_type": str(item.get("question_type") or "calculation"),
                "title": normalize_short_inline_display_math(str(item.get("title") or item.get("stem") or "")),
                "options": [
                    normalize_question_math({"options": [option]}).get("options", [option])[0]
                    for option in item.get("options")
                ] if isinstance(item.get("options"), list) else [],
                "answer": normalize_short_inline_display_math(str(item.get("answer") or "")),
                "analysis": normalize_short_inline_display_math(str(item.get("analysis") or "")),
                "sub_questions": item.get("sub_questions") if isinstance(item.get("sub_questions"), list) else [],
                "figures": item.get("figures") if isinstance(item.get("figures"), list) else [],
                "difficulty": item.get("difficulty"),
                "knowledge_point": str(item.get("knowledge_point") or ""),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "source": str(item.get("source") or source),
                "import_batch_id": str(item.get("import_batch_id") or batch_id),
                "confidence": item.get("confidence"),
                "source_page": item.get("source_page"),
                "source_region_id": item.get("source_region_id"),
                "raw_text": item.get("raw_text"),
            })
        )
    return normalized


def extract_json_payload(text: str) -> Any | None:
    candidates = [text.strip()]
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        candidates.append(match.group(1).strip())

    for candidate in candidates:
        if not candidate:
            continue
        start = min(
            [pos for pos in (candidate.find("{"), candidate.find("[")) if pos >= 0],
            default=-1,
        )
        if start < 0:
            continue
        try:
            return json.loads(candidate[start:])
        except json.JSONDecodeError:
            continue
    return None


def safe_json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def normalize_knowledge_draft(raw: Any, batch_id: str, index: int, source_text: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or raw.get("topic3_name") or raw.get("name") or "").strip()
    if not title:
        return None
    draft_id = str(raw.get("draft_id") or raw.get("topic3_id") or f"{batch_id}_k{index:04d}")
    tags = raw.get("tags")
    return {
        "draft_id": draft_id,
        "topic3_id": str(raw.get("topic3_id") or draft_id).strip(),
        "topic3_name": title,
        "topic2_id": str(raw.get("topic2_id") or raw.get("parent_id") or "").strip(),
        "topic2_name": str(raw.get("topic2_name") or raw.get("module") or "").strip(),
        "topic1_id": str(raw.get("topic1_id") or "").strip(),
        "topic1_name": str(raw.get("topic1_name") or "").strip(),
        "source_chapter": str(raw.get("source_chapter") or raw.get("chapter") or "").strip(),
        "definition": str(raw.get("definition") or raw.get("content") or "").strip(),
        "formula": str(raw.get("formula") or "").strip(),
        "key_summary": str(raw.get("key_summary") or raw.get("summary") or "").strip(),
        "error_prone": str(raw.get("error_prone") or raw.get("common_mistakes") or "").strip(),
        "example_analysis": str(raw.get("example_analysis") or raw.get("example") or "").strip(),
        "tags": [str(item) for item in tags] if isinstance(tags, list) else [],
        "raw_text": source_text,
        "status": "pending",
    }


def extract_generated_knowledge_drafts(source_text: str, batch_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    json_payload = extract_json_payload(source_text)
    candidates: list[Any] = []
    if isinstance(json_payload, dict):
        raw_items = json_payload.get("knowledge_drafts") or json_payload.get("knowledge_points")
        if isinstance(raw_items, list):
            candidates.extend(raw_items)
        else:
            candidates.append(json_payload)
    elif isinstance(json_payload, list):
        candidates.extend(json_payload)

    drafts = [
        draft
        for index, item in enumerate(candidates, start=1)
        if (draft := normalize_knowledge_draft(item, batch_id, index, source_text)) is not None
    ]
    if drafts:
        return drafts, warnings

    if re.search(r"(知识点|定义|公式|易错|核心|考点|key_summary|definition|formula|error_prone)", source_text):
        title_match = re.search(r"(?:知识点|标题|考点)\s*[：:]\s*([^\n]+)", source_text)
        title = title_match.group(1).strip() if title_match else source_text.strip().splitlines()[0][:60]
        drafts.append(
            {
                "draft_id": f"{batch_id}_k0001",
                "topic3_id": f"{batch_id}_k0001",
                "topic3_name": title,
                "topic2_id": "",
                "topic2_name": "",
                "topic1_id": "",
                "topic1_name": "",
                "source_chapter": "",
                "definition": source_text.strip(),
                "formula": "",
                "key_summary": "",
                "error_prone": "",
                "example_analysis": "",
                "tags": [],
                "raw_text": source_text,
                "status": "pending",
            }
        )
        warnings.append("已按知识点文本整理为待审核草稿，建议补全章节层级和标准知识点 ID。")
    return drafts, warnings


def looks_like_knowledge_review(source_text: str) -> bool:
    payload = extract_json_payload(source_text)
    if isinstance(payload, dict):
        if "knowledge_drafts" in payload or "knowledge_points" in payload:
            return True
        knowledge_keys = {"definition", "formula", "key_summary", "error_prone", "topic3_name"}
        question_keys = {"answer", "options", "question_body", "question_type"}
        if knowledge_keys.intersection(payload) and not question_keys.intersection(payload):
            return True
    return bool(
        re.search(r"(知识点|定义|核心公式|易错点|标准表述)", source_text)
        and not re.search(r"(答案|选项|A\.|B\.|题干|参考答案)", source_text)
    )


def metadata_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": question.get("question_id", ""),
        "question_type": question.get("question_type", ""),
        "title": question.get("title", ""),
        "options": question.get("options", []),
        "answer": question.get("answer", ""),
        "analysis": question.get("analysis", ""),
        "knowledge_point": question.get("knowledge_point", ""),
        "tags": question.get("tags", []),
        "source": question.get("source", ""),
    }


def parse_draft_metadata_result(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items")
    if not isinstance(items, list):
        items = raw.get("questions") or raw.get("metadata")
    if not isinstance(items, list) or not items:
        raw_text = str(raw.get("text") or "").strip()
        if raw_text:
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, list):
                    items = parsed
                elif isinstance(parsed, dict):
                    items = parsed.get("items") or parsed.get("questions") or parsed.get("metadata") or []
            except json.JSONDecodeError:
                items = []
    if not isinstance(items, list):
        return {}

    parsed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or item.get("id") or "").strip()
        if not question_id:
            continue
        entry: dict[str, Any] = {}
        knowledge = item.get("knowledge_points", item.get("knowledgePoints", item.get("knowledge_point")))
        if isinstance(knowledge, list) and knowledge:
            entry["knowledge_points"] = str(knowledge[0]).strip()
        elif isinstance(knowledge, str) and knowledge.strip():
            entry["knowledge_points"] = knowledge.strip()
        tags = item.get("tags")
        if isinstance(tags, list):
            entry["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        source = item.get("source")
        if isinstance(source, str) and source.strip():
            entry["source"] = source.strip()
        parsed[question_id] = entry
    return parsed


def merge_draft_metadata(
    question: dict[str, Any],
    patch: dict[str, Any],
    fields: list[str],
    force_overwrite: bool,
) -> tuple[dict[str, Any], bool]:
    merged = dict(question)
    changed = False

    if "knowledge_points" in fields:
        value = str(patch.get("knowledge_points") or "").strip()
        if value and (force_overwrite or not str(merged.get("knowledge_point") or "").strip()):
            merged["knowledge_point"] = value
            changed = True
    if "tags" in fields:
        tags = patch.get("tags") if isinstance(patch.get("tags"), list) else []
        tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        existing = merged.get("tags") if isinstance(merged.get("tags"), list) else []
        if tags and (force_overwrite or not existing):
            merged["tags"] = tags if force_overwrite else list(dict.fromkeys([*existing, *tags]))
            changed = True
    if "source" in fields:
        value = str(patch.get("source") or "").strip()
        if value and (force_overwrite or not str(merged.get("source") or "").strip()):
            merged["source"] = value
            changed = True
    return merged, changed
