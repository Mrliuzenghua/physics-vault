"""AI refinement for imported question drafts.

This module keeps model calls split into small batches with bounded
concurrency. A failed or slow batch falls back to the local parser output, so
one model issue cannot block the whole import workflow.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any, Callable

from .math_text import normalize_question_math

logger = logging.getLogger(__name__)

AllowedCall = Callable[..., dict[str, Any]]

QUESTION_TYPES = {"single_choice", "multi_choice", "fill", "experiment", "calculation"}

REFINE_SYSTEM_PROMPT = """你是高中物理题库结构化校对助手。

输入是本地程序已经切分出的题目 JSON 数组。你的任务是在不新增、不删除、不合并、不拆分题目的前提下，逐题清理题干、选项、答案和解析，并返回可直接进入校对中心的 JSON。

必须只返回 JSON 对象：
{
  "questions": [
    {
      "question_id": "保持输入原值",
      "question_type": "single_choice | multi_choice | fill | experiment | calculation",
      "title": "题干，保留原有 ![fig:xxx] 图片占位符",
      "options": [{"opt": "A", "content": "..."}],
      "answer": "...",
      "analysis": "..."
    }
  ]
}

规则：
1. question_id 必须与输入一一对应，顺序和数量不变。
2. 必须保留 ![fig:xxx] 图片占位符，不要改名、删除或移动到其他题。
3. title 只放题干和必要图片占位符，把混入题干的选项、答案、解析移到对应字段。
4. options.content 不要保留 A.、B.、（A）等前缀。
5. answer 尽量简洁；选择题用连续大写字母，如 D 或 BD。
6. analysis 如果原文没有解析可以为空，不要编造长解析。
7. 公式使用 LaTeX：行内 $...$，块公式 $$...$$。
8. 明显不是完整题目的页眉、页脚、目录、残段，title 置为空字符串。
9. 不要输出 Markdown 代码块，不要输出解释。"""


def refine_import_questions_concurrent(
    *,
    questions: list[dict[str, Any]],
    call: AllowedCall,
    batch_size: int = 5,
    max_workers: int = 3,
    time_budget_seconds: float = 240.0,
) -> dict[str, Any]:
    if not questions:
        return {"questions": [], "refined_count": 0}

    batches = [
        (start, questions[start : start + batch_size])
        for start in range(0, len(questions), batch_size)
    ]
    workers = max(1, min(max_workers, len(batches)))
    started_at = time.monotonic()

    completed: dict[int, tuple[list[dict[str, Any]], int]] = {}
    executor = ThreadPoolExecutor(max_workers=workers)
    future_map: dict[Future[tuple[int, list[dict[str, Any]], int]], int] = {}

    try:
        for start, batch in batches:
            future = executor.submit(_refine_one_batch, start, batch, call)
            future_map[future] = start

        done, pending = wait(future_map.keys(), timeout=time_budget_seconds)
        for future in done:
            start = future_map[future]
            try:
                completed_start, refined_batch, refined_count = future.result()
                completed[completed_start] = (refined_batch, refined_count)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AI refine batch %d failed after completion: %s", start, exc)

        if pending:
            logger.warning(
                "AI refine time budget %.0fs exceeded; %d unfinished batches keep local results",
                time_budget_seconds,
                len(pending),
            )
            for future in pending:
                future.cancel()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    refined: list[dict[str, Any]] = []
    refined_count_total = 0
    for start, batch in batches:
        refined_batch, refined_count = completed.get(start, (batch, 0))
        refined.extend(normalize_question_math(item) for item in refined_batch)
        refined_count_total += refined_count

    logger.info(
        "AI refine finished: %d/%d questions refined in %.1fs",
        refined_count_total,
        len(questions),
        time.monotonic() - started_at,
    )
    return {"questions": refined, "refined_count": refined_count_total}


def _refine_one_batch(
    start: int,
    batch: list[dict[str, Any]],
    call: AllowedCall,
) -> tuple[int, list[dict[str, Any]], int]:
    payload = [_compact_question(item) for item in batch]
    batch_started = time.monotonic()
    try:
        result = call(
            [
                {"role": "system", "content": REFINE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=12000,
            response_format={"type": "json_object"},
            timeout_seconds=90,
        )
        items = result.get("questions")
        if not isinstance(items, list):
            raise ValueError("AI response missing 'questions' array")
        logger.info(
            "AI refine batch %d-%d done in %.1fs",
            start + 1,
            start + len(batch),
            time.monotonic() - batch_started,
        )
        return _merge_batch(start, batch, items)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI refine failed for batch %d-%d: %s", start + 1, start + len(batch), exc)
        return start, batch, 0


def _compact_question(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": question.get("question_id", ""),
        "question_type": question.get("question_type", "calculation"),
        "title": question.get("title", ""),
        "options": question.get("options", []),
        "answer": question.get("answer", ""),
        "analysis": question.get("analysis", ""),
        "figures": question.get("figures", []),
    }


def _merge_batch(
    start: int,
    local_batch: list[dict[str, Any]],
    ai_items: list[Any],
) -> tuple[int, list[dict[str, Any]], int]:
    by_id = {
        str(item.get("question_id", "")): item
        for item in ai_items
        if isinstance(item, dict)
    }
    refined: list[dict[str, Any]] = []
    refined_count = 0

    for local_question in local_batch:
        ai_question = by_id.get(str(local_question.get("question_id", "")))
        if ai_question is None:
            refined.append(local_question)
            continue

        merged = dict(local_question)
        title = str(ai_question.get("title", "")).strip()
        if title:
            merged["title"] = title

        q_type = str(ai_question.get("question_type", "")).strip()
        if q_type in QUESTION_TYPES:
            merged["question_type"] = q_type

        ai_options = ai_question.get("options")
        if isinstance(ai_options, list) and ai_options:
            options = [
                {"opt": str(item.get("opt", "")).strip(), "content": str(item.get("content", "")).strip()}
                for item in ai_options
                if isinstance(item, dict) and str(item.get("opt", "")).strip()
            ]
            if options:
                merged["options"] = options

        for field in ("answer", "analysis"):
            value = str(ai_question.get(field, "")).strip()
            if value:
                merged[field] = value

        merged["_ai_refined"] = True
        refined_count += 1
        refined.append(normalize_question_math(merged))

    return start, refined, refined_count
