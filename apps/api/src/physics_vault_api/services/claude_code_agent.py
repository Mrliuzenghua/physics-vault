from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

from ..paths import default_db_path, default_review_db_path, project_root
from ..repositories.question_search import QuestionSearchRepository
from ..schemas.agents import (
    AgentAction,
    AgentConfig,
    AgentConfigResponse,
    AgentStreamEvent,
    AgentTestResponse,
    AgentTraceStep,
    QuestionPickerAgentRequest,
    QuestionPickerAgentResponse,
    ReviewLatexCleanupResponse,
)
from ..schemas.ai_assistant import AiAssistantQuestionContext
from .ai_assistant import (
    _build_composition_suggestions,
    _build_rule_based_reply,
    _candidate_query_tokens,
    _latest_user_text,
    _row_to_context,
)
from .math_text import normalize_math_delimiters

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(
    os.getenv(
        "PHYSICS_AGENT_CONFIG_PATH",
        project_root() / "data" / "agent_config.json",
    )
)
_SESSION_LOCKS: dict[str, asyncio.Lock] = {}
_KNOWN_SESSION_IDS: set[str] = set()


class ClaudeCodeAgentService:
    def __init__(self, repository: QuestionSearchRepository | None = None) -> None:
        self._repo = repository or QuestionSearchRepository()

    def get_config(self) -> AgentConfigResponse:
        config = _load_config()
        ok, message, _version = _check_claude_code(config)
        return AgentConfigResponse(config=config, available=ok, message=message)

    def update_config(self, config: AgentConfig) -> AgentConfigResponse:
        normalized = AgentConfig(
            claude_code_path=config.claude_code_path.strip(),
            enabled=config.enabled,
            timeout_seconds=config.timeout_seconds,
        )
        _save_config(normalized)
        ok, message, _version = _check_claude_code(normalized)
        return AgentConfigResponse(config=normalized, available=ok, message=message)

    def test_claude_code(self) -> AgentTestResponse:
        config = _load_config()
        ok, message, version = _check_claude_code(config)
        return AgentTestResponse(ok=ok, message=message, version=version)

    def cleanup_review_latex(
        self,
        *,
        task_id: str | None = None,
        user_text: str | None = None,
        dry_run: bool = False,
    ) -> ReviewLatexCleanupResponse:
        started = time.perf_counter()
        resolved_task_id = (task_id or "").strip() or _resolve_review_latex_cleanup_task_id(user_text or "")
        if not resolved_task_id:
            return ReviewLatexCleanupResponse(
                ok=False,
                dry_run=dry_run,
                error="没有定位到可清洗的校对任务。",
                message="请打开具体校对任务，或说明题目数量，例如“那 15 道送审题”。",
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        result = _clean_review_task_latex_artifacts(resolved_task_id, dry_run=dry_run)
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        result["fast_path"] = True
        result["dry_run"] = dry_run
        result.setdefault("message", "预览完成，未写入审核草稿。" if dry_run else "已快速清洗审核草稿。")
        return ReviewLatexCleanupResponse(**result)

    async def pick_questions(self, request: QuestionPickerAgentRequest) -> QuestionPickerAgentResponse:
        final_response: QuestionPickerAgentResponse | None = None
        async for event in self.stream_pick_questions(request):
            if event.type == "response" and event.response:
                final_response = event.response
        if final_response is None:
            raise RuntimeError("智能体没有返回结果")
        return final_response

    async def stream_pick_questions(
        self,
        request: QuestionPickerAgentRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        user_text = _latest_user_text(request)
        query = (request.query or user_text).strip()
        is_review_center_request = _is_review_center_request(user_text)
        conversational_reply = _conversational_reply(user_text)
        current_review_task_id = _current_review_task_id(request)
        session_id = _normalize_session_id(request.session_id)
        trace: list[AgentTraceStep] = []
        warnings: list[str] = []
        cache_step = AgentTraceStep(
            title="复用对话缓存",
            detail=f"Claude Code 会话 {session_id[:8]}，本轮会带上最近对话和固定上下文。",
            status="done",
        )

        step = AgentTraceStep(title="读取对话目标", detail=f"本轮需求：{user_text[:180]}", status="done")
        trace.append(step)
        yield AgentStreamEvent(type="trace", step=step)
        trace.append(cache_step)
        yield AgentStreamEvent(type="trace", step=cache_step)

        if conversational_reply:
            step = AgentTraceStep(
                title="识别普通对话",
                detail="这不是选题、查库或校对任务，直接回复，不调用 Claude Code，也不检索题库。",
                status="done",
            )
            trace.append(step)
            yield AgentStreamEvent(type="trace", step=step)
            yield AgentStreamEvent(
                type="response",
                response=QuestionPickerAgentResponse(
                    reply=conversational_reply,
                    session_id=session_id,
                    query_used=query,
                    selected_questions=[],
                    actions=[],
                    warnings=[],
                    trace=trace,
                ),
            )
            return

        if current_review_task_id and _is_direct_review_latex_cleanup_request(request, user_text):
            result = _clean_review_task_latex_artifacts(current_review_task_id)
            step = AgentTraceStep(
                title="直接清洗校对任务",
                detail=(
                    f"已按当前页面 task_id={current_review_task_id} 直接更新校对草稿数据库；"
                    f"影响 {result.get('changed_questions', 0)} 道题，替换 {result.get('replacement_count', 0)} 处。"
                ),
                status="done" if result.get("ok") else "error",
            )
            trace.append(step)
            yield AgentStreamEvent(type="trace", step=step)
            yield AgentStreamEvent(
                type="response",
                response=QuestionPickerAgentResponse(
                    reply=_build_latex_cleanup_reply(result),
                    session_id=session_id,
                    query_used=query,
                    selected_questions=[],
                    actions=[],
                    warnings=[] if result.get("ok") else [str(result.get("error") or "清洗失败")],
                    trace=trace,
                ),
            )
            return

        if _is_review_latex_cleanup_request(user_text):
            resolved_review_task_id = current_review_task_id or _resolve_review_latex_cleanup_task_id(user_text)
            if resolved_review_task_id:
                result = _clean_review_task_latex_artifacts(resolved_review_task_id)
                step = AgentTraceStep(
                    title="直接处理送审草稿",
                    detail=(
                        f"识别为校对/送审任务的 LaTeX 清洗，已使用审核库 task_id={resolved_review_task_id}；"
                        f"不检索正式题库。影响 {result.get('changed_questions', 0)} 道题，替换 "
                        f"{result.get('replacement_count', 0)} 处。"
                    ),
                    status="done" if result.get("ok") else "error",
                )
                trace.append(step)
                yield AgentStreamEvent(type="trace", step=step)
                yield AgentStreamEvent(
                    type="response",
                    response=QuestionPickerAgentResponse(
                        reply=_build_latex_cleanup_reply(result),
                        session_id=session_id,
                        query_used=query,
                        selected_questions=[],
                        actions=[],
                        warnings=[] if result.get("ok") else [str(result.get("error") or "清洗失败")],
                        trace=trace,
                    ),
                )
                return

        cached_context = self._cached_context(request.context_question_ids)
        if cached_context:
            step = AgentTraceStep(
                title="载入上下文缓存",
                detail=f"已固定 {len(cached_context)} 道题，本轮会优先作为 Claude Code 候选上下文。",
                status="done",
            )
            trace.append(step)
            yield AgentStreamEvent(type="trace", step=step)

        config = _load_config()
        ok, message, _version = _check_claude_code(config)
        if config.enabled and ok:
            context = cached_context[: max(request.context_limit, len(cached_context))]
            step = AgentTraceStep(
                title="交给 Claude 判断查库",
                detail=(
                    f"已带入 {len(context)} 道固定上下文题；"
                    "本轮不预检索候选题，由 Claude Code 按需通过 MCP 主动查库。"
                ),
                status="done",
            )
            trace.append(step)
            yield AgentStreamEvent(type="trace", step=step)
        else:
            context = self._merge_context(
                cached_context,
                self._search_context(query, request.context_limit),
                request.context_limit,
            )
            search_terms = _candidate_query_tokens(query)
            step = AgentTraceStep(
                title="检索数据库题目",
                detail=(
                    f"检索词：{query or '自动浏览'}；"
                    f"{'智能扩展标签：' + '、'.join(search_terms[:6]) + '；' if search_terms else ''}"
                    f"找到 {len(context)} 道候选题。"
                ),
                status="done" if context else "warning",
            )
            trace.append(step)
            yield AgentStreamEvent(type="trace", step=step)

        suggestions = _build_composition_suggestions(context)
        fallback_reply = _build_rule_based_reply(user_text, context, suggestions)
        fallback_actions = _actions_from_questions(context, "加入推荐题目")

        if not config.enabled:
            warning = "Claude Code 智能体未启用，已使用题库规则选题。"
            warnings.append(warning)
            step = AgentTraceStep(
                title="使用规则选题",
                detail="系统根据题库命中和难度分布生成建议。",
                status="warning",
            )
            trace.append(step)
            yield AgentStreamEvent(type="warning", message=warning)
            yield AgentStreamEvent(type="trace", step=step)
            yield AgentStreamEvent(
                type="response",
                response=QuestionPickerAgentResponse(
                    reply=fallback_reply,
                    session_id=session_id,
                    query_used=query,
                    selected_questions=context[: min(8, len(context))],
                    actions=fallback_actions,
                    warnings=warnings,
                    trace=trace,
                ),
            )
            return

        if not ok:
            warning = f"Claude Code 不可用：{message}。已使用题库规则选题。"
            warnings.append(warning)
            step = AgentTraceStep(title="智能体不可用", detail=message, status="warning")
            trace.append(step)
            yield AgentStreamEvent(type="warning", message=warning)
            yield AgentStreamEvent(type="trace", step=step)
            yield AgentStreamEvent(
                type="response",
                response=QuestionPickerAgentResponse(
                    reply=fallback_reply,
                    session_id=session_id,
                    query_used=query,
                    selected_questions=context[: min(8, len(context))],
                    actions=fallback_actions,
                    warnings=warnings,
                    trace=trace,
                ),
            )
            return

        prompt = _build_question_picker_prompt(request, context)
        step = AgentTraceStep(
            title="启动 Claude Code",
            detail=f"已传入 {len(context)} 道固定上下文题；Claude Code 会按需通过 MCP 主动查库。",
            status="done",
        )
        trace.append(step)
        yield AgentStreamEvent(type="trace", step=step)

        raw_parts: list[str] = []
        try:
            async with _session_lock(session_id):
                resume_session = request.resume_session or session_id in _KNOWN_SESSION_IDS
                _KNOWN_SESSION_IDS.add(session_id)
                async for chunk in _run_claude_print_stream(
                    config,
                    prompt,
                    session_id=session_id,
                    resume_session=resume_session,
                ):
                    raw_parts.append(chunk)
                    yield AgentStreamEvent(type="terminal", message=chunk)

            raw = "\n".join(raw_parts).strip()
            parsed, parse_warning = _coerce_agent_json(raw)
            selected_ids = [str(item).strip() for item in parsed.get("question_ids", []) if str(item).strip()]
            selected = self._select_context_by_ids(context, selected_ids) or context[: min(8, len(context))]
            actions = _actions_from_questions(selected, "加入智能体选题")

            if parse_warning:
                warnings.append(f"Claude Code 输出已自动整理：{parse_warning}")

            step = AgentTraceStep(
                title="整理输出" if parse_warning else "解析结果",
                detail=f"Claude Code 建议 {len(selected_ids)} 个题号，最终匹配到 {len(selected)} 道题。",
                status="warning" if parse_warning else ("done" if selected else "warning"),
            )
            trace.append(step)
            yield AgentStreamEvent(type="trace", step=step)
            yield AgentStreamEvent(
                type="response",
                response=QuestionPickerAgentResponse(
                    reply=str(parsed.get("reply") or fallback_reply).strip(),
                    agent_used=True,
                    agent_name="Claude Code",
                    session_id=session_id,
                    query_used=query,
                    selected_questions=selected,
                    actions=actions,
                    warnings=warnings,
                    trace=trace,
                    raw_agent_text=raw[:4000],
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Claude Code question picker failed: %s", exc)
            safe_error = _friendly_agent_error(exc)
            if is_review_center_request:
                current_task_id = _current_review_task_id(request)
                if current_task_id:
                    current_task = _review_task_snapshot(current_task_id)
                    if current_task.get("ok"):
                        step = AgentTraceStep(
                            title="读取当前校对任务",
                            detail=(
                                f"Claude Code 未完成，系统已根据当前页面 task_id={current_task_id} "
                                "直接读取校对任务摘要。"
                            ),
                            status="done",
                        )
                        trace.append(step)
                        yield AgentStreamEvent(type="trace", step=step)
                        yield AgentStreamEvent(
                            type="response",
                            response=QuestionPickerAgentResponse(
                                reply=_build_current_review_task_reply(current_task, RuntimeError(safe_error)),
                                session_id=session_id,
                                query_used=query,
                                selected_questions=[],
                                actions=[],
                                warnings=[],
                                trace=trace,
                            ),
                        )
                        return

                snapshot = _review_center_snapshot()
                reply = _build_review_center_fallback_reply(RuntimeError(safe_error), snapshot)
                fallback_step = AgentTraceStep(
                    title="识别校对中心请求",
                    detail=(
                        "本轮目标是清洗校对中心题目，应由 Claude Code 通过 MCP 查看校对队列或草稿任务；"
                        "调用失败时不再用正式题库检索结果替代。"
                    ),
                    status="warning",
                )
                trace.append(fallback_step)
                yield AgentStreamEvent(type="trace", step=fallback_step)
                step = AgentTraceStep(title="调用失败", detail=safe_error, status="error")
                trace.append(step)
                yield AgentStreamEvent(type="trace", step=step)
                yield AgentStreamEvent(
                    type="response",
                    response=QuestionPickerAgentResponse(
                        reply=reply,
                        session_id=session_id,
                        query_used=query,
                        selected_questions=[],
                        actions=[],
                        warnings=warnings,
                        trace=trace,
                    ),
                )
                return
            fallback_context = context
            if not fallback_context:
                fallback_context = self._merge_context(
                    cached_context,
                    self._search_context(query, request.context_limit),
                    request.context_limit,
                )
                fallback_suggestions = _build_composition_suggestions(fallback_context)
                fallback_reply = _build_rule_based_reply(user_text, fallback_context, fallback_suggestions)
                fallback_actions = _actions_from_questions(fallback_context, "加入推荐题目")
                fallback_step = AgentTraceStep(
                    title="兜底检索数据库",
                    detail=f"Claude Code 调用失败后，系统用规则检索找到 {len(fallback_context)} 道候选题。",
                    status="done" if fallback_context else "warning",
                )
                trace.append(fallback_step)
                yield AgentStreamEvent(type="trace", step=fallback_step)
            warning = f"Claude Code 调用失败，已使用题库规则选题：{safe_error}"
            warnings.append(warning)
            step = AgentTraceStep(title="调用失败", detail=safe_error, status="error")
            trace.append(step)
            yield AgentStreamEvent(type="warning", message=warning)
            yield AgentStreamEvent(type="trace", step=step)
            yield AgentStreamEvent(
                type="response",
                response=QuestionPickerAgentResponse(
                    reply=fallback_reply,
                    session_id=session_id,
                    query_used=query,
                    selected_questions=fallback_context[: min(8, len(fallback_context))],
                    actions=fallback_actions,
                    warnings=warnings,
                    trace=trace,
                ),
            )

    def _search_context(self, query: str, limit: int) -> list[AiAssistantQuestionContext]:
        rows = self._search_rows(query, limit)
        tokens = _candidate_query_tokens(query) if query else []
        if not rows and tokens:
            for token in tokens:
                rows = self._search_rows(token, limit)
                if rows:
                    break
        if not rows and not tokens:
            rows = self._browse_rows(limit)
        return [_row_to_context(row) for row in rows[:limit]]

    def _cached_context(self, question_ids: list[str]) -> list[AiAssistantQuestionContext]:
        clean_ids = list(dict.fromkeys(qid.strip() for qid in question_ids if qid.strip()))
        if not clean_ids:
            return []
        rows = self._repo.get_questions_by_ids(clean_ids)
        return [_row_to_context(row) for row in rows]

    def _merge_context(
        self,
        cached: list[AiAssistantQuestionContext],
        searched: list[AiAssistantQuestionContext],
        limit: int,
    ) -> list[AiAssistantQuestionContext]:
        merged: list[AiAssistantQuestionContext] = []
        seen: set[str] = set()
        for item in [*cached, *searched]:
            if not item.question_id or item.question_id in seen:
                continue
            seen.add(item.question_id)
            merged.append(item)
        return merged[: max(limit, len(cached))]

    def _search_rows(self, query: str, limit: int) -> list[dict]:
        if not query.strip():
            return []
        rows, _ = self._repo.search_questions(
            search_mode="strict",
            query=query.strip(),
            year=None,
            module=None,
            question_type=None,
            difficulty=None,
            status=None,
            topic1_id=None,
            topic2_id=None,
            topic3_id=None,
            topic2=None,
            topic3=None,
            region=None,
            exam_type=None,
            has_media=None,
            image_count_min=0,
            is_mistake=None,
            limit=limit,
            offset=0,
        )
        return rows

    def _browse_rows(self, limit: int) -> list[dict]:
        rows, _ = self._repo.search_questions(
            search_mode="browse",
            query=None,
            year=None,
            module=None,
            question_type=None,
            difficulty=None,
            status=None,
            topic1_id=None,
            topic2_id=None,
            topic3_id=None,
            topic2=None,
            topic3=None,
            region=None,
            exam_type=None,
            has_media=None,
            image_count_min=0,
            is_mistake=None,
            limit=limit,
            offset=0,
        )
        return rows

    def _select_context_by_ids(
        self,
        context: list[AiAssistantQuestionContext],
        question_ids: list[str],
    ) -> list[AiAssistantQuestionContext]:
        by_id = {item.question_id: item for item in context}
        missing_ids = [qid for qid in question_ids if qid not in by_id]
        if missing_ids:
            for row in self._repo.get_questions_by_ids(missing_ids):
                item = _row_to_context(row)
                if item.question_id:
                    by_id[item.question_id] = item
        return [by_id[qid] for qid in question_ids if qid in by_id]


_REVIEW_CENTER_RE = re.compile(
    r"(检验页|检验中心|全部风险|修复.*风险|消除.*风险)|"
    r"(校对中心|待校对|审核任务|审核队列|回炉|复核|送审|已送审|草稿任务|清洗.*校对|校对.*清洗)"
)
_REVIEW_LATEX_REQUEST_RE = re.compile(
    r"(送审|已送审|校对中心|校对任务|审核任务|草稿).*(latex|LaTeX|公式|结构化|格式|清洗|处理)|"
    r"(latex|LaTeX|公式|结构化|格式|清洗|处理).*(送审|已送审|校对中心|校对任务|审核任务|草稿)"
)
_COUNT_RE = re.compile(r"(\d+)\s*[道到個个題题]|\b(\d+)\b")
_CASUAL_TEXT_RE = re.compile(r"^[\s,，。.!！?？~～]*(你好|您好|hello|hi|嗨|在吗|在不在|谢谢|谢了|辛苦了)[\s,，。.!！?？~～]*$", re.IGNORECASE)
_MATH_ITALIC_RE = re.compile(r"(?<!\*)\*([A-Za-z][A-Za-z0-9_{}\\]*(?:\s*[-+/]\s*[A-Za-z][A-Za-z0-9_{}\\]*)?)\*(?!\*)")
_OCR_TABLE_BORDER_RE = re.compile(r"^\s*-{3,}(?:\s+-{3,})+\s*$")
_MATH_CELL_RE = re.compile(r"\$[^$]+\$")
_TEXT_KEYS_FOR_LATEX_CLEANUP = {
    "title",
    "stem",
    "question_body",
    "analysis",
    "answer",
    "raw_text",
    "content",
    "text",
}


def _is_review_center_request(text: str) -> bool:
    return bool(_REVIEW_CENTER_RE.search(text or ""))


def _is_review_latex_cleanup_request(text: str) -> bool:
    return bool(_REVIEW_LATEX_REQUEST_RE.search(text or ""))


def _requested_review_count(text: str) -> int | None:
    for match in _COUNT_RE.finditer(text or ""):
        raw = match.group(1) or match.group(2)
        if not raw:
            continue
        count = int(raw)
        if 1 <= count <= 200:
            return count
    return None


def _resolve_review_latex_cleanup_task_id(text: str) -> str | None:
    db_path = default_review_db_path()
    if not db_path.exists():
        return None
    requested_count = _requested_review_count(text)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _sqlite_table_exists(conn, "import_pipeline_tasks"):
                return None
            rows = conn.execute(
                """
                SELECT task_id, task_type, status, updated_at, created_at,
                       input_summary_json, result_json
                FROM import_pipeline_tasks
                WHERE task_type IN ('import_confirmed', 'ai_generated_review')
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 30
                """
            ).fetchall()
        candidates: list[tuple[str, int, str]] = []
        for row in rows:
            result = _safe_json_dict(row["result_json"])
            summary = _safe_json_dict(row["input_summary_json"])
            questions = result.get("questions") if isinstance(result.get("questions"), list) else []
            question_count = int(result.get("question_count") or summary.get("question_count") or len(questions) or 0)
            if question_count <= 0:
                continue
            if requested_count is not None and question_count != requested_count:
                continue
            candidates.append((str(row["task_id"]), question_count, str(row["updated_at"] or row["created_at"] or "")))
        if not candidates:
            return None
        return candidates[0][0]
    except Exception:
        return None


def _is_direct_review_latex_cleanup_request(request: QuestionPickerAgentRequest, user_text: str) -> bool:
    source = "\n".join(message.content for message in request.messages[-8:])
    wants_direct_write = (
        ("直接" in user_text or "就在" in user_text or "执行" in user_text)
        and (
            "数据库" in user_text
            or "这里" in user_text
            or "这个" in user_text
            or "草稿" in user_text
            or "校对" in user_text
        )
        and ("修改" in user_text or "改" in user_text or "清洗" in user_text)
    )
    has_latex_context = any(marker in source for marker in ("latex", "LaTeX", "公式", "格式", "清洗")) or bool(
        _MATH_ITALIC_RE.search(source)
    )
    has_review_context = "校对中心" in source or "当前校对任务" in source
    return wants_direct_write and has_latex_context and has_review_context


def _current_review_task_id(request: QuestionPickerAgentRequest) -> str | None:
    for message in request.messages:
        if message.role != "system":
            continue
        match = re.search(r"当前校对任务\s*task_id[：:]\s*([A-Za-z0-9_-]{6,120})", message.content)
        if match:
            return match.group(1).strip()
        match = re.search(r"/review/([A-Za-z0-9_-]{6,120})", message.content)
        if match:
            return match.group(1).strip()
    return None


def _conversational_reply(text: str) -> str | None:
    source = (text or "").strip()
    if not source:
        return "我在。你可以直接说要找题、清洗校对中心、整理标签，或者问我当前页面能做什么。"
    if not _CASUAL_TEXT_RE.match(source):
        return None
    normalized = source.lower()
    if "谢" in source:
        return "不客气。我在这儿，继续说你要处理哪一页或哪批题就行。"
    if "在吗" in source or "在不在" in source:
        return "在。我会结合你当前所在页面来回答；如果要查题库或校对中心，我再调用对应工具。"
    return "你好，我在。你可以直接说要找题、清洗校对中心、整理知识目录或标签；我会先看当前页面语境，再决定要不要查数据库。"


def _clean_review_task_latex_artifacts(task_id: str, *, dry_run: bool = False) -> dict[str, object]:
    db_path = default_review_db_path()
    if not db_path.exists():
        return {"ok": False, "task_id": task_id, "error": "审核数据库文件不存在"}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT result_json
                FROM import_pipeline_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "task_id": task_id, "error": "当前校对任务不存在"}
            result = _safe_json_dict(row["result_json"])
            questions = result.get("questions") if isinstance(result.get("questions"), list) else []
            changed_questions: list[dict[str, object]] = []
            total_replacements = 0

            for raw in questions:
                if not isinstance(raw, dict):
                    continue
                before = json.dumps(raw, ensure_ascii=False, sort_keys=True)
                cleaned, replacements = _clean_latex_in_value(raw)
                if isinstance(cleaned, dict):
                    raw.clear()
                    raw.update(cleaned)
                after = json.dumps(raw, ensure_ascii=False, sort_keys=True)
                if before != after:
                    qid = str(raw.get("question_id") or raw.get("id") or "").strip()
                    changed_questions.append({"question_id": qid, "replacements": replacements})
                    total_replacements += replacements

            if changed_questions and not dry_run:
                result["questions"] = questions
                history = result.get("cleanup_history")
                if not isinstance(history, list):
                    history = []
                history.append(
                    {
                        "source": "ai_assistant_direct_cleanup",
                        "kind": "markdown_italic_to_latex",
                        "changed_questions": len(changed_questions),
                        "replacement_count": total_replacements,
                    }
                )
                result["cleanup_history"] = history[-20:]
                conn.execute(
                    """
                    UPDATE import_pipeline_tasks
                    SET result_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE task_id = ?
                    """,
                    (json.dumps(result, ensure_ascii=False), task_id),
                )
                conn.commit()

        return {
            "ok": True,
            "task_id": task_id,
            "dry_run": dry_run,
            "changed_questions": len(changed_questions),
            "replacement_count": total_replacements,
            "items": changed_questions,
            "message": "预览完成，未写入审核草稿。" if dry_run else "已快速清洗审核草稿。",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "task_id": task_id, "error": str(exc)}


def _clean_latex_in_value(value: object, key: str | None = None) -> tuple[object, int]:
    if isinstance(value, str):
        if key is not None and key not in _TEXT_KEYS_FOR_LATEX_CLEANUP:
            return value, 0
        cleaned, table_count = _normalize_ocr_tables_in_text(value)
        cleaned, italic_count = _replace_markdown_math_italics(cleaned)
        return cleaned, table_count + italic_count
    if isinstance(value, list):
        changed: list[object] = []
        count = 0
        for item in value:
            cleaned, replacements = _clean_latex_in_value(item, key=None)
            changed.append(cleaned)
            count += replacements
        return changed, count
    if isinstance(value, dict):
        changed: dict[str, object] = {}
        count = 0
        for item_key, item_value in value.items():
            cleaned, replacements = _clean_latex_in_value(item_value, key=str(item_key))
            changed[item_key] = cleaned
            count += replacements
        return changed, count
    return value, 0


def _replace_markdown_math_italics(text: str) -> tuple[str, int]:
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        expr = " ".join(match.group(1).split())
        if not expr or len(expr) > 16:
            return match.group(0)
        count += 1
        return f"${expr}$"

    cleaned = _MATH_ITALIC_RE.sub(repl, text)
    cleaned, delimiter_count = normalize_math_delimiters(cleaned)
    return cleaned, count + delimiter_count


def _normalize_ocr_tables_in_text(text: str) -> tuple[str, int]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    count = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if _OCR_TABLE_BORDER_RE.match(line):
            parsed = _parse_ocr_table(lines, index)
            if parsed is not None:
                table_lines, next_index = parsed
                output.extend(table_lines)
                count += 1
                index = next_index
                continue
        output.append(line)
        index += 1
    return "\n".join(output), count


def _parse_ocr_table(lines: list[str], start_index: int) -> tuple[list[str], int] | None:
    column_count = len(re.findall(r"-{3,}", lines[start_index]))
    if column_count < 2:
        return None

    end_index = start_index + 1
    while end_index < len(lines) and not _OCR_TABLE_BORDER_RE.match(lines[end_index]):
        end_index += 1
    if end_index >= len(lines):
        return None

    body_lines = [line.strip() for line in lines[start_index + 1 : end_index] if line.strip()]
    if len(body_lines) < 2:
        return None

    rows = [_split_ocr_table_row(line, column_count) for line in body_lines]
    if any(row is None for row in rows):
        return None

    safe_rows = [row for row in rows if row is not None]
    table_lines = [
        _markdown_table_row(safe_rows[0]),
        _markdown_table_row(["---"] * column_count),
        *[_markdown_table_row(row) for row in safe_rows[1:]],
    ]
    return table_lines, end_index + 1


def _split_ocr_table_row(line: str, column_count: int) -> list[str] | None:
    math_cells = _MATH_CELL_RE.findall(line)
    if len(math_cells) == column_count:
        leftover = line
        for cell in math_cells:
            leftover = leftover.replace(cell, " ", 1)
        if not leftover.strip():
            return [cell.strip() for cell in math_cells]

    wide_space_cells = [cell.strip() for cell in re.split(r"\t+|\s{2,}", line.strip()) if cell.strip()]
    if len(wide_space_cells) == column_count:
        return wide_space_cells

    if column_count == 2:
        compact_cells = [cell.strip() for cell in line.strip().split() if cell.strip()]
        if len(compact_cells) == 2:
            return compact_cells

    return None


def _markdown_table_row(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def _build_latex_cleanup_reply(result: dict[str, object]) -> str:
    if not result.get("ok"):
        return f"这次没有写入成功：{result.get('error') or '未知错误'}"
    changed = int(result.get("changed_questions") or 0)
    replacements = int(result.get("replacement_count") or 0)
    items = result.get("items") if isinstance(result.get("items"), list) else []
    lines = [
        "已直接在当前校对任务数据库里完成 LaTeX 格式清洗。",
        f"任务 ID：{result.get('task_id')}",
        f"影响题目：{changed} 道；替换 Markdown 斜体变量：{replacements} 处。",
    ]
    if items:
        lines.append("已修改题号：" + "、".join(str(item.get("question_id")) for item in items if isinstance(item, dict)))
    lines.append("这次只改校对中心草稿，不改正式题库。刷新校对页面后可以看到更新后的文本。")
    return "\n".join(lines)


def _review_task_snapshot(task_id: str, limit: int = 6) -> dict[str, object]:
    db_path = default_db_path()
    if not db_path.exists():
        return {"ok": False, "task_id": task_id, "error": "数据库文件不存在"}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _sqlite_table_exists(conn, "import_pipeline_tasks"):
                return {"ok": False, "task_id": task_id, "error": "校对任务表不存在"}
            row = conn.execute(
                """
                SELECT task_id, task_type, status, created_at, updated_at,
                       input_summary_json, result_json, error
                FROM import_pipeline_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return {"ok": False, "task_id": task_id, "error": "当前页面任务 ID 在数据库里不存在"}
        summary = _safe_json_dict(row["input_summary_json"])
        result = _safe_json_dict(row["result_json"])
        questions = result.get("questions") if isinstance(result.get("questions"), list) else []
        knowledge_drafts = result.get("knowledge_drafts") if isinstance(result.get("knowledge_drafts"), list) else []
        items: list[dict[str, object]] = []
        for index, raw in enumerate(questions[: max(1, min(limit, 20))], start=1):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("stem") or raw.get("question_body") or "").strip()
            knowledge = raw.get("knowledge_point") or raw.get("knowledge_points") or ""
            items.append(
                {
                    "index": index,
                    "question_id": str(raw.get("question_id") or raw.get("id") or "").strip(),
                    "title": " ".join(title.split())[:120],
                    "answer": str(raw.get("answer") or "").strip()[:80],
                    "knowledge": knowledge,
                    "status": str(raw.get("review_status") or raw.get("status") or "pending"),
                }
            )
        return {
            "ok": True,
            "task_id": row["task_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "batch_id": str(result.get("batch_id") or summary.get("batch_id") or ""),
            "question_count": int(result.get("question_count") or summary.get("question_count") or len(questions)),
            "knowledge_count": int(result.get("knowledge_count") or summary.get("knowledge_count") or len(knowledge_drafts)),
            "warnings": [str(item) for item in result.get("warnings") or []],
            "items": items,
            "error": row["error"],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "task_id": task_id, "error": str(exc)}


def _build_current_review_task_reply(snapshot: dict[str, object], exc: Exception) -> str:
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    lines = [
        "能读。刚才 Claude Code 没跑完，但我已经根据当前页面的任务 ID 直接读取了校对中心任务。",
        "",
        f"当前任务：{snapshot.get('task_id')}",
        f"状态：{snapshot.get('status')}；题目 {snapshot.get('question_count', 0)} 道，知识点 {snapshot.get('knowledge_count', 0)} 个。",
    ]
    if snapshot.get("batch_id"):
        lines.append(f"批次：{snapshot.get('batch_id')}")
    if items:
        lines.extend(["", "前几道题摘要："])
        for item in items[:6]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "（无题干摘要）"
            qid = item.get("question_id") or f"第 {item.get('index')} 题"
            lines.append(f"- {qid}：{title}")
    lines.extend(
        [
            "",
            "所以这里不是空的，也不是那 3 条 DEMO 队列。你要我继续清洗的话，我会按当前这批草稿题处理。",
        ]
    )
    if str(exc):
        lines.append(f"Claude Code 未完成原因：{exc}")
    return "\n".join(lines)


def _review_center_snapshot(limit: int = 5) -> dict[str, object]:
    db_path = default_review_db_path()
    snapshot: dict[str, object] = {
        "review_queue_pending": 0,
        "review_tasks_total": 0,
        "review_tasks": [],
        "review_database_path": str(db_path),
        "canonical_database_path": str(default_db_path()),
    }
    if not db_path.exists():
        snapshot["error"] = "数据库文件不存在"
        return snapshot
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if _sqlite_table_exists(conn, "review_queue"):
                snapshot["review_queue_pending"] = int(
                    conn.execute("SELECT COUNT(*) FROM review_queue WHERE status = 'pending'").fetchone()[0]
                )
            if _sqlite_table_exists(conn, "import_pipeline_tasks"):
                rows = conn.execute(
                    """
                    SELECT task_id, task_type, status, created_at, updated_at,
                           input_summary_json, result_json, error
                    FROM import_pipeline_tasks
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(limit or 5), 20)),),
                ).fetchall()
                snapshot["review_tasks_total"] = int(
                    conn.execute("SELECT COUNT(*) FROM import_pipeline_tasks").fetchone()[0]
                )
                tasks = []
                for row in rows:
                    summary = _safe_json_dict(row["input_summary_json"])
                    result = _safe_json_dict(row["result_json"])
                    tasks.append(
                        {
                            "task_id": row["task_id"],
                            "task_type": row["task_type"],
                            "status": row["status"],
                            "title": str(
                                result.get("title")
                                or result.get("source")
                                or summary.get("source")
                                or ("AI 生成审核" if row["task_type"] == "ai_generated_review" else "导入校对任务")
                            ),
                            "question_count": int(result.get("question_count") or summary.get("question_count") or 0),
                            "knowledge_count": int(result.get("knowledge_count") or summary.get("knowledge_count") or 0),
                            "updated_at": row["updated_at"],
                            "error": row["error"],
                        }
                    )
                snapshot["review_tasks"] = tasks
    except Exception as exc:  # noqa: BLE001
        snapshot["error"] = str(exc)
    return snapshot


def _build_review_center_fallback_reply(exc: Exception, snapshot: dict[str, object]) -> str:
    if snapshot.get("error"):
        return (
            "这是校对中心清洗任务，不应该用正式题库检索来替代。"
            f"这次 Claude Code 没跑完：{exc}。我尝试读取校对中心摘要时也遇到问题：{snapshot['error']}。"
        )
    tasks = snapshot.get("review_tasks")
    task_lines: list[str] = []
    if isinstance(tasks, list):
        for task in tasks[:5]:
            if not isinstance(task, dict):
                continue
            task_lines.append(
                f"- {task.get('title') or task.get('task_id')}：{task.get('question_count', 0)} 题，"
                f"{task.get('knowledge_count', 0)} 个知识点，状态 {task.get('status')}"
            )
    summary = (
        f"我识别这是校对中心清洗任务，不会拿正式题库搜索结果兜底。"
        f"当前校对队列待处理约 {snapshot.get('review_queue_pending', 0)} 条，"
        f"校对任务表共有 {snapshot.get('review_tasks_total', 0)} 个任务。"
    )
    if task_lines:
        summary += "\n最近任务：\n" + "\n".join(task_lines)
    summary += f"\nClaude Code 这次调用失败：{exc}。请重新点一次，我会让它通过 MCP 直接查看校对中心任务。"
    return summary


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _safe_json_dict(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_config() -> AgentConfig:
    try:
        if _CONFIG_FILE.exists():
            return AgentConfig.model_validate(json.loads(_CONFIG_FILE.read_text("utf-8")))
    except Exception:
        logger.warning("Failed to load agent config from %s", _CONFIG_FILE)
    return AgentConfig(
        claude_code_path=os.getenv("PHYSICS_CLAUDE_CODE_PATH", ""),
        enabled=bool(os.getenv("PHYSICS_CLAUDE_CODE_PATH")),
    )


def _save_config(config: AgentConfig) -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(config.model_dump_json(indent=2), "utf-8")


def _resolve_executable(path: str) -> str | None:
    raw = path.strip().strip('"')
    if not raw:
        return None
    resolved = shutil.which(raw)
    if resolved:
        return resolved
    candidate = Path(raw)
    if candidate.exists() and candidate.is_file():
        return str(candidate)
    return None


def _check_claude_code(config: AgentConfig) -> tuple[bool, str, str | None]:
    executable = _resolve_executable(config.claude_code_path)
    if not executable:
        return False, "请配置 Claude Code 可执行文件路径，例如 claude、claude.cmd 或完整路径。", None
    try:
        completed = subprocess.run(
            [executable, "--version"],
            cwd=str(project_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        if completed.returncode != 0:
            return False, output or f"Claude Code 退出码 {completed.returncode}", output or None
        return True, output or "Claude Code 可用", output or None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), None


async def _run_claude_print_stream(
    config: AgentConfig,
    prompt: str,
    *,
    session_id: str | None = None,
    resume_session: bool = False,
    allow_session_fallback: bool = True,
) -> AsyncIterator[str]:
    # On Windows, uvicorn may run on an event loop that cannot create async
    # subprocesses. Run the Claude CLI in a worker thread with subprocess.run
    # instead; we still expose the completed output as terminal lines.
    output = await asyncio.to_thread(
        _run_claude_print_with_fallback,
        config,
        prompt,
        session_id=session_id,
        resume_session=resume_session,
        allow_session_fallback=allow_session_fallback,
    )
    for line in output.splitlines():
        text = line.strip()
        if text:
            yield text


def _run_claude_print_with_fallback(
    config: AgentConfig,
    prompt: str,
    *,
    session_id: str | None = None,
    resume_session: bool = False,
    allow_session_fallback: bool = True,
) -> str:
    try:
        return _run_claude_print(config, prompt, session_id=session_id, resume_session=resume_session)
    except RuntimeError as exc:
        output = str(exc)
        fallback_resume = _fallback_resume_mode(output, resume_session)
        if session_id and allow_session_fallback and fallback_resume is not None:
            note = "Claude Code 会话恢复失败，已自动切换会话模式。"
            recovered = _run_claude_print(
                config,
                prompt,
                session_id=session_id,
                resume_session=fallback_resume,
            )
            return f"{note}\n{recovered}".strip()
        raise


def _run_claude_print(
    config: AgentConfig,
    prompt: str,
    *,
    session_id: str | None = None,
    resume_session: bool = False,
) -> str:
    executable = _resolve_executable(config.claude_code_path)
    if not executable:
        raise RuntimeError("Claude Code 路径未配置")
    args = [executable, "-p", prompt, "--output-format", "text"]
    mcp_config = _mcp_config_path()
    if mcp_config.exists():
        args.extend(["--mcp-config", str(mcp_config)])
    if session_id:
        args.extend(["--resume" if resume_session else "--session-id", session_id])
    completed = subprocess.run(
        args,
        cwd=str(project_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=config.timeout_seconds,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        raise RuntimeError(output or f"Claude Code 退出码 {completed.returncode}")
    return output


def _build_question_picker_prompt(
    request: QuestionPickerAgentRequest,
    context: list[AiAssistantQuestionContext],
) -> str:
    user_text = _latest_user_text(request)
    page_context = _build_system_context(request)
    conversation_digest = _build_conversation_digest(request)
    context_json = [item.model_dump() for item in context]
    quality_instruction = "如果当前页面上下文包含前端校验诊断，清洗时必须逐题反馈 question_id、字段、规则 code、严重程度、原问题和修改建议；不要只说存在风险。题目已被用户编辑时，依据最新诊断和完整题目重新判断，已解决的问题不要重复报告。"
    return f"""你是 Physics Vault 的本地选题智能体，负责帮高中物理老师从本地题库选题、改编题目和准备送审内容。

你可以主动使用 MCP 数据库工具查库：
- `mcp__physics_vault__search_questions`：按关键词、题型、难度、章节、知识点等检索正式题库。
- `mcp__physics_vault__search_knowledge_points` / `mcp__physics_vault__list_knowledge_tree`：先找标准考点名和 topic id，再查题。
- `mcp__physics_vault__maintain_question_knowledge_points`：当检索结果的题干/解析与现有知识点明显冲突、知识点缺失或只标了一个但还有明确辅助考点时调用。每题采用 1 个主知识点加最多 2 个辅助三级知识点；auto_fix=true 只会自动落库高置信度修复，疑难项保留待复核并返回可回滚审计批次。不要为了凑满三个而添加弱相关知识点。
- `mcp__physics_vault__get_questions_by_ids`：按题号回读完整题目。
- `mcp__physics_vault__find_similar_questions`：围绕某道题查同类题。
- `mcp__physics_vault__submit_ai_generated_review`：只在用户要求生成、改编或送审 AI 内容时使用，把内容送入审核草稿，禁止写正式题库。
- `mcp__physics_vault__import_word_folder_to_review`：当用户明确要求处理某个文件夹中的 Word 文件时使用。先以 `dry_run=true` 列出 .doc/.docx 文件和数量；用户确认后再用 `dry_run=false` 依次导入、清洗、结构化并生成审核库任务。不得搜索文件夹后自行猜测或直接写 SQLite。
- `mcp__physics_vault__list_composition_workbenches` / `get_composition_workbench`：读取已保存的组卷工作台草稿；不传 draft_id 时读取最近编辑的一份。
- `mcp__physics_vault__create_composition_workbench`：新建独立组卷草稿。先 dry_run=true 预览，确认后才 dry_run=false。
- `mcp__physics_vault__add_questions_to_composition_workbench`：把已入正式题库的 question_id 引用加入组卷工作台；只写草稿，绝不修改题库题目。
- `mcp__physics_vault__add_knowledge_to_composition_workbench`：只引用已有知识目录，不生成讲解。老师要求生成知识讲解时不要调用它，也不要用近似 topic3_id 代替实际考点。
- `mcp__physics_vault__insert_teaching_block_to_composition_workbench`：插入试卷标题、姓名栏、分节标题或教学说明文字；只写草稿。组卷工作台是自由编排区，老师明确要求时可直接执行，不需要审核或二次确认。
- `mcp__physics_vault__reorder_composition_workbench`：按完整 item id 顺序重排题目、知识卡与教学对象；先读取草稿获得 item id，再 dry_run=true 预览，确认后才执行。
- `mcp__physics_vault__apply_composition_workbench_plan`：组卷操作的优先接口。老师要求“为工作台题目生成知识讲解”时，每个考点使用一个 knowledge operation，填写简洁标题、非空 content/summary 和 related_question_ids。内容必须结合对应题目的实际判断过程，讲清关键规律、必要公式和本题易错点，使用自然段或少量有意义的小标题；禁止套用“概念与条件、规律与表达、解题路径、常见误区”之类固定模板。不要再生成“通用知识卡 + 独立讲解文本”两块重复内容。只有目录节点语义完全一致时才传 topic3_id，没有准确节点就只传 title。已有同 topic3_id 的旧讲解会原位更新。老师已明确要求编辑工作台时直接 dry_run=false，并用 ordered_refs 将讲解排在对应题目后。
- `mcp__physics_vault__curate_questions_to_composition_workbench`：当老师说“找全部某主题题目并精选 N 道组卷”时优先使用。一次检索正式题库候选题，排除当前工作台已有题，再按题型、难度、来源覆盖度做均衡精选，直接给出组卷预览；先 dry_run=true，确认后再写入草稿。
- `mcp__physics_vault__list_review_queue`：查看审核库校对队列 review_queue，适合“待校对、回炉、人工复核、打回修复”的任务。
- `mcp__physics_vault__list_review_tasks`：查看导入/AI 生成后进入校对中心的草稿任务，适合“送审的题目”“那 15 道送审题”“清洗校对中心题目/知识点草稿”的任务；可用 question_count=15 精确定位。
- `mcp__physics_vault__get_review_task`：快速读取某个校对中心任务的草稿摘要。
- `mcp__physics_vault__get_review_task_full`：需要检查长题干、LaTeX 或完整字段时读取完整草稿；不要只依赖 preview。
- `mcp__physics_vault__validate_review_task`：在解释、清洗或提交校对题目前先调用，按 question_id 读取结构化风险、字段、规则 code、严重程度、原问题和修改建议；只关心问题题目时使用 risks_only=true；题目修改后重新调用，不要继续使用旧诊断。工具支持唯一 task_id 前缀，但后续必须改用返回的完整 task_id。老师明确要求“消除/修复风险”时，必须继续调用修改工具，不能只返回建议；若仍有风险，必须继续由 MCP 读取完整题目、逐字段生成补丁并写回草稿，不能让老师自行处理。
- `mcp__physics_vault__split_merged_options`：从 raw_text 中识别并拆分被 OCR 合并的 A/B/C/D 选项；先 dry_run=true 预览，老师明确要求修复时再 dry_run=false 写回当前 task。
- `mcp__physics_vault__clean_review_task_latex`：清理当前校对草稿中的 Markdown 斜体公式；先 dry_run=true，确认后才写入当前草稿。若清洗后仍有 LaTeX 风险，不能止步于提示。
- `mcp__physics_vault__update_review_task_draft`：按 question_id 直接更新当前校对草稿字段；默认先 dry_run=true，老师明确要求消除/修复风险时可直接 dry_run=false。处理残留 LaTeX 风险时，必须先用 get_review_task_full 读取题目，再为受影响的 title、stem、options、answer 或 analysis 逐题写回补丁：行内公式统一为 $...$，独立块公式统一为 $$...$$，分隔符开闭成对且不能混用。写回后必须再次 validate_review_task。当前草稿的修改不能通过 submit_ai_generated_review 伪装成新任务。
- `mcp__physics_vault__database_boundary_report`：不确定该查正式库还是审核库时先用它；它会返回正式库/审核库路径、职责边界、遗留污染和推荐工具路由。
- `mcp__physics_vault__database_health_report`：盘点正式题库健康度，并附带审核库摘要；不要用正式库里的历史 review_queue 判断校对中心。
- `mcp__physics_vault__list_question_tags`：盘点题目标签和标签频次，适合先发现标签混乱、重复、口径不一致的问题。
- `mcp__physics_vault__batch_replace_question_tags`：批量替换正式题库标签；必须先 dry_run=true 预览修改前后，只有用户明确要求“应用/执行/落库/确认修改”时才允许 dry_run=false。
- `mcp__physics_vault__return_question_to_review`：把正式题打回校对中心；必须先 dry_run=true 预览，只有用户明确确认时才允许 dry_run=false。
- `mcp__physics_vault__batch_replace_question_knowledge_points`：批量替换题目绑定的正式知识目录；必须先 dry_run=true 预览，确认后才允许 dry_run=false。
重要边界：当前页面已经打开具体校对任务时，先用当前 task_id 读取和修改这份草稿；不要重新 submit_ai_generated_review 生成重复任务。只有用户要求生成全新题目或把新内容送审时，才使用 submit_ai_generated_review。
正式题库写入边界：只有标签替换、知识目录绑定替换、题目打回校对这三类受控工具可以修改正式数据库。所有写库工具必须先 dry_run=true，向老师说明修改原因、修改前后、影响题数；没有明确确认，不得 dry_run=false。整理标签时先说明收紧原则，例如去重、合并同义词、保留知识目录相关标签、最多保留少量高价值标签。知识目录绑定以 `knowledge_points` 和 `question_knowledge_points` 为准，`questions.module/topic2/topic3` 只作兼容展示。
校对中心硬边界：如果用户说“送审、已送审、那 15 道送审题、校对中心、待校对、审核任务、草稿、回炉、清洗审核任务、清洗校对中心题目、公式/LaTeX 结构化”，第一步必须使用审核库工具 `list_review_tasks`、`list_review_queue` 或 `get_review_task`。禁止先调用正式库工具 `search_questions`、`get_questions_by_ids`、`database_health_report` 来定位这批题；这些题可能尚未入库，正式库找不到是正常现象。只有用户明确说“正式题库找题/组卷/换题/已入库题目”时才走正式题库检索。
当前页面上下文优先级：最近对话摘要里的“系统: 当前页面...”是前端自动注入的页面上下文，优先级高于普通历史聊天。老师说“这里、当前、这批、这套、这个页面”时，必须先结合当前页面含义判断任务范围。若出现“当前页面：校对中心任务页”或“当前校对任务 task_id”，说明老师正在打开某个具体校对任务。此时必须先调用 `get_review_task(task_id)` 读取当前任务；长题干、完整 LaTeX 或需要修改时改用 `get_review_task_full(task_id)`，不要只根据 `list_review_tasks` 的全局列表说“校对中心为空”。
普通对话边界：如果用户只是问候、确认你是否在线、表示感谢，直接自然回应，不要查库，不要选题，不要输出“没找到题目”。

下方 JSON 只包含用户固定到对话里的上下文题，可能为空；它不是系统替你预检索出的候选集。你需要先判断用户任务是否必须查询正式题库：如果需要找题、组卷、换题、查同类题或核对题号，请你自己选择检索词/知识点并调用 MCP 查库；如果只是解释固定上下文或整理已给内容，可以不查库。最终不要编造题号，question_ids 只能来自固定上下文 JSON 或 MCP 查询结果。

元数据自治规则（优先于上方旧工具兼容说明）：
- 标签、知识点绑定、难度、题型、规范化来源、年份、地区和试卷类型属于检索元数据。使用 `mcp__physics_vault__batch_update_question_metadata` 直接整理，不需要 dry_run 或再次询问用户；知识点变更会自动记录可回滚审计批次。
- 正式题目应优先维护 1 个主三级知识点，并在题干或解析有明确证据时补充最多 2 个辅助三级知识点。检索到疑似错标题时，先调用 `maintain_question_knowledge_points`；高置信度错误直接修复，needs_review 项不得强行改写。
- 导入后优先使用 `mcp__physics_vault__organize_knowledge_tree` 一次完成已有节点复用、缺失节点创建和题目绑定；处理校对草稿时必须传当前 task_id。不得创建同名重复节点，也不要要求老师手工维护目录。
- `mcp__physics_vault__suggest_knowledge_points_for_task` 仅用于只读诊断；只有用户明确要求查看候选结果时才单独调用。
- 导入文件夹时默认 `skip_if_duplicate=true`；需要清理历史重复任务时，先用 `find_duplicate_review_tasks`，删除必须通过 `delete_review_tasks(confirmed=true)`。
- 原始来源、正式题目题干、选项、答案、解析、图片和发布状态不属于自治元数据，不得通过元数据工具修改。审核草稿发布到正式题库始终由老师在 UI 完成。

用户需求：
{user_text}

当前页面上下文：
{page_context}
{quality_instruction}

最近对话摘要：
{conversation_digest}

固定上下文题 JSON：
{json.dumps(context_json, ensure_ascii=False, indent=2)}

只返回一个 JSON 对象，不要 Markdown，不要代码块。reply 字段必须是普通字符串，换行请用 \\n。如果没有真实工具返回的 task_id，不要在 reply 里写“已提交”“审核任务 ID”“审核入口”或 `/review/...`：
{{"reply":"给老师看的中文说明，解释为什么这样选、建议讲课或练习顺序","question_ids":["从候选题或 MCP 查询结果中选择的 question_id，最多 10 个"]}}
"""


def _build_conversation_digest(request: QuestionPickerAgentRequest, limit: int = 8) -> str:
    rows: list[str] = []
    for message in request.messages[-limit:]:
        content = " ".join(message.content.split())
        if not content:
            continue
        if len(content) > 420:
            content = f"{content[:420]}..."
        role = {"user": "用户", "assistant": "AI", "system": "系统"}.get(message.role, message.role)
        rows.append(f"{role}: {content}")
    return "\n".join(rows) or "（无历史对话）"


def _build_system_context(request: QuestionPickerAgentRequest) -> str:
    rows: list[str] = []
    for message in request.messages:
        if message.role != "system":
            continue
        content = " ".join(message.content.split())
        if not content:
            continue
        if len(content) > 1200:
            content = f"{content[:1200]}..."
        rows.append(content)
    return "\n".join(rows) or "（无页面上下文）"


def _normalize_session_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value.strip()))
        except (TypeError, ValueError):
            logger.warning("Invalid Claude Code session id ignored: %s", value)
    return str(uuid4())


def _session_lock(session_id: str) -> asyncio.Lock:
    lock = _SESSION_LOCKS.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _SESSION_LOCKS[session_id] = lock
    return lock


def _mcp_config_path() -> Path:
    dedicated = project_root() / ".claude" / "physics-vault-agent-mcp.json"
    return dedicated if dedicated.exists() else project_root() / ".claude" / "physics-vault-mcp.json"


def _fallback_resume_mode(output: str, attempted_resume: bool) -> bool | None:
    normalized = output.lower()
    if attempted_resume and "no conversation found with session id" in normalized:
        return False
    if not attempted_resume and "session id" in normalized and "already in use" in normalized:
        return True
    return None


def _friendly_agent_error(exc: Exception) -> str:
    """Keep process details in logs, but show an actionable message in the chat UI."""
    raw = str(exc or "").strip()
    lowered = raw.lower()
    if isinstance(exc, TimeoutError) or "timed out" in lowered or "timeout" in lowered:
        return "Claude Code 响应超时；当前任务已保留，稍后可重试。"
    if "command '[" in lowered or "filenotfounderror" in lowered or "winerror" in lowered:
        return "Claude Code 进程启动失败；请检查 Claude Code 路径和专用 MCP 配置。"
    if not raw:
        return "Claude Code 返回了空错误。"
    return raw[:240]


def _extract_agent_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Claude Code 未返回 JSON 对象")
    return parsed


def _coerce_agent_json(raw: str) -> tuple[dict, str | None]:
    try:
        return _extract_agent_json(raw), None
    except Exception as exc:  # noqa: BLE001
        reply = _extract_reply_text(raw) or _strip_json_wrapper(raw)
        ids = _extract_question_ids(raw)
        return {"reply": reply, "question_ids": ids}, str(exc)


def _extract_reply_text(raw: str) -> str:
    match = re.search(r'"reply"\s*:\s*"(?P<reply>.*?)(?:"\s*,\s*"question_ids")', raw, re.S)
    if not match:
        return ""
    return (
        match.group("reply")
        .replace("\\n", "\n")
        .replace('\\"', '"')
        .replace("\\/", "/")
        .strip()
    )


def _extract_question_ids(raw: str) -> list[str]:
    ids: list[str] = []
    for match in re.finditer(r'(?:batch|q|question)[-_][0-9A-Za-z_:-]+', raw):
        value = match.group(0).rstrip('",，。；;')
        if value not in ids:
            ids.append(value)
    return ids[:10]


def _strip_json_wrapper(raw: str) -> str:
    text = raw.strip().strip("`").strip()
    if text.lower().startswith("json"):
        text = text[4:].strip()
    return text[:2400]


def _actions_from_questions(
    questions: list[AiAssistantQuestionContext],
    label: str,
) -> list[AgentAction]:
    ids = [item.question_id for item in questions if item.question_id]
    if not ids:
        return []
    return [
        AgentAction(
            action_id=f"act_{uuid4().hex[:10]}",
            type="add_to_basket",
            label=label,
            question_ids=ids,
            payload={"source": "question_picker_agent"},
            requires_confirmation=True,
        ),
        AgentAction(
            action_id=f"act_{uuid4().hex[:10]}",
            type="open_questions",
            label="查看这些题目",
            question_ids=ids,
            payload={"source": "question_picker_agent"},
            requires_confirmation=False,
        ),
    ]
