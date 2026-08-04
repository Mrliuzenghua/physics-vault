from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from openai import OpenAI

from ..repositories.question_search import QuestionSearchRepository
from ..runtime_config import get_runtime_config
from ..schemas.ai_assistant import (
    AiAssistantChatRequest,
    AiAssistantChatResponse,
    AiAssistantQuestionContext,
    CompositionSuggestion,
)


class AiAssistantService:
    def __init__(self, repository: QuestionSearchRepository | None = None) -> None:
        self._repo = repository or QuestionSearchRepository()

    async def chat(self, request: AiAssistantChatRequest) -> AiAssistantChatResponse:
        user_text = _latest_user_text(request)
        query = (request.query or user_text).strip()
        context = self._search_context(query, request.context_limit)
        suggestions = _build_composition_suggestions(context)

        fallback_reply = _build_rule_based_reply(user_text, context, suggestions)
        runtime = get_runtime_config()
        warnings: list[str] = []

        if not runtime.llm.api_key.strip() or not runtime.llm.base_url.strip() or not runtime.llm.model_name.strip():
            warnings.append("AI 文本模型尚未配置，已基于题库检索结果给出规则建议。")
            return AiAssistantChatResponse(
                reply=fallback_reply,
                context_questions=context,
                composition_suggestions=suggestions,
                query_used=query,
                warnings=warnings,
            )

        try:
            client = OpenAI(
                api_key=runtime.llm.api_key,
                base_url=runtime.llm.base_url,
                timeout=min(runtime.llm.timeout_seconds, 15),
                max_retries=0,
            )
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=runtime.llm.model_name,
                messages=_build_model_messages(request, context, suggestions),
                temperature=request.temperature,
            )
            reply = response.choices[0].message.content if response.choices else ""
            return AiAssistantChatResponse(
                reply=(reply or fallback_reply).strip(),
                model=response.model or runtime.llm.model_name,
                ai_used=True,
                query_used=query,
                context_questions=context,
                composition_suggestions=suggestions,
                warnings=warnings,
                usage=response.usage.model_dump() if response.usage else None,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"AI 调用失败，已返回题库规则建议：{exc}")
            return AiAssistantChatResponse(
                reply=fallback_reply,
                model=runtime.llm.model_name,
                ai_used=False,
                query_used=query,
                context_questions=context,
                composition_suggestions=suggestions,
                warnings=warnings,
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

    def _search_rows(self, query: str, limit: int) -> list[dict[str, Any]]:
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

    def _browse_rows(self, limit: int) -> list[dict[str, Any]]:
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


def _latest_user_text(request: AiAssistantChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content.strip()
    return request.messages[-1].content.strip()


def _candidate_query_tokens(text: str) -> list[str]:
    source = _strip_search_intent_words(text)
    terms = _domain_search_terms(source)

    separators = "，。！？、；：,.!?;:\n\t "
    tokens: list[str] = []
    current = ""
    for char in source:
        if char in separators:
            if len(current.strip()) >= 2:
                tokens.append(current.strip())
            current = ""
        else:
            current += char
    if len(current.strip()) >= 2:
        tokens.append(current.strip())

    preferred = [
        token
        for token in tokens
        if any(keyword in token for keyword in ["力", "电", "磁", "运动", "能量", "动量", "电路", "光", "实验", "加速度", "原子", "能级"])
    ]
    ordered = terms + preferred + [token for token in tokens if token not in preferred]
    result: list[str] = []
    for token in ordered:
        clean = token.strip()
        if len(clean) >= 2 and clean not in result:
            result.append(clean)
    return result


def _domain_search_terms(source: str) -> list[str]:
    term_map: list[tuple[str, list[str]]] = [
        ("氢原子能级", ["氢原子能级", "氢原子", "能级跃迁", "玻尔模型", "光谱", "能级"]),
        ("氢原子", ["氢原子", "氢原子能级", "玻尔模型", "能级"]),
        ("原子能级", ["原子能级", "能级跃迁", "光谱", "能级"]),
        ("能级跃迁", ["能级跃迁", "能级", "光子", "光谱"]),
        ("万有引力", ["万有引力", "引力", "天体运动", "卫星", "开普勒"]),
        ("开普勒第三定律", ["开普勒第三定律", "开普勒", "周期", "轨道半径", "天体运动"]),
        ("牛顿第二定律", ["牛顿第二定律", "合力", "加速度", "动力学"]),
        ("闭合电路欧姆定律", ["闭合电路欧姆定律", "闭合电路", "电动势", "内阻", "路端电压"]),
        ("机械能守恒", ["机械能守恒", "动能", "势能", "能量守恒"]),
        ("动量守恒", ["动量守恒", "碰撞", "冲量", "动量"]),
        ("电磁感应", ["电磁感应", "法拉第", "楞次定律", "感应电流", "感应电动势"]),
        ("简谐振动", ["简谐振动", "振幅", "周期", "回复力"]),
        ("圆周运动", ["圆周运动", "向心力", "向心加速度"]),
        ("平抛运动", ["平抛运动", "抛体运动", "水平位移"]),
        ("带电粒子", ["带电粒子", "电场偏转", "磁场偏转", "洛伦兹力"]),
        ("交流电", ["交流电", "变压器", "有效值", "峰值"]),
        ("静电场", ["静电场", "电场强度", "电势", "电势能"]),
        ("磁场", ["磁场", "洛伦兹力", "安培力"]),
        ("光电效应", ["光电效应", "逸出功", "截止频率", "光电子"]),
    ]
    terms: list[str] = []
    for key, values in term_map:
        if key in source:
            terms.extend(values)
    if "能级" in source:
        terms.append("能级")
    if "原子" in source:
        terms.append("原子")
    result: list[str] = []
    for term in terms:
        if term not in result:
            result.append(term)
    return result


def _strip_search_intent_words(text: str) -> str:
    source = text.strip()
    replacements = [
        "帮我",
        "请",
        "找一个",
        "找一份",
        "找一道",
        "找几道",
        "找",
        "检索",
        "搜索",
        "有没有",
        "一个",
        "一道",
        "几道",
        "相关",
        "关于",
        "考查",
        "考",
        "的题目",
        "的题",
        "题目",
        "试题",
        "例题",
        "课堂",
        "给我",
    ]
    for word in replacements:
        source = source.replace(word, " ")
    return " ".join(source.split())


def _row_to_context(row: dict[str, Any]) -> AiAssistantQuestionContext:
    tags = row.get("tags_json") or row.get("tags") or []
    if isinstance(tags, str):
        try:
            import json

            tags = json.loads(tags)
        except Exception:  # noqa: BLE001
            tags = []
    knowledge_points = row.get("knowledge_points") or []
    kp_name = row.get("topic3") or row.get("knowledge_point")
    if not kp_name and knowledge_points:
        first = knowledge_points[0]
        if isinstance(first, dict):
            kp_name = first.get("topic3_name") or first.get("topic2_name") or first.get("topic1_name")

    return AiAssistantQuestionContext(
        question_id=str(row.get("question_id") or ""),
        title=str(row.get("canonical_title") or row.get("title") or row.get("stem_text") or ""),
        question_type=row.get("question_type"),
        difficulty=str(row.get("difficulty")) if row.get("difficulty") is not None else None,
        knowledge_point=kp_name,
        source=row.get("primary_paper_id") or row.get("source") or row.get("paper_region"),
        answer=row.get("answer_text") or row.get("answer"),
        analysis=row.get("analysis_text") or row.get("analysis"),
        tags=[str(tag) for tag in tags if str(tag).strip()],
    )


def _build_composition_suggestions(
    questions: list[AiAssistantQuestionContext],
) -> list[CompositionSuggestion]:
    if not questions:
        return []

    type_counter = Counter(q.question_type or "unknown" for q in questions)
    difficulty_mix = Counter(_difficulty_bucket(q.difficulty) for q in questions)
    score = sum(_score_for_type(q.question_type) for q in questions)
    question_ids = [q.question_id for q in questions if q.question_id]
    main_kp = Counter(q.knowledge_point for q in questions if q.knowledge_point).most_common(1)
    topic = main_kp[0][0] if main_kp else "当前检索主题"

    suggestions = [
        CompositionSuggestion(
            title=f"{topic}专项训练",
            rationale="优先使用检索到的同主题题目，适合快速形成一份课堂练习或课后巩固。",
            question_ids=question_ids[: min(8, len(question_ids))],
            estimated_score=score,
            difficulty_mix=dict(difficulty_mix),
        )
    ]

    if len(type_counter) >= 2:
        suggestions.append(
            CompositionSuggestion(
                title="题型混合小测",
                rationale="当前上下文包含多种题型，可以按先基础选择、再计算/实验的顺序组织。",
                question_ids=question_ids[: min(6, len(question_ids))],
                estimated_score=sum(_score_for_type(q.question_type) for q in questions[:6]),
                difficulty_mix=dict(Counter(_difficulty_bucket(q.difficulty) for q in questions[:6])),
            )
        )

    return suggestions


def _score_for_type(question_type: str | None) -> int:
    return {
        "single_choice": 5,
        "multi_choice": 6,
        "fill": 5,
        "experiment": 10,
        "calculation": 12,
    }.get(question_type or "", 5)


def _difficulty_bucket(value: str | None) -> str:
    try:
        num = float(value or 0)
    except ValueError:
        return "未标注"
    if num <= 0:
        return "未标注"
    if num <= 2:
        return "基础"
    if num <= 4:
        return "中档"
    return "压轴"


def _build_rule_based_reply(
    user_text: str,
    context: list[AiAssistantQuestionContext],
    suggestions: list[CompositionSuggestion],
) -> str:
    if not context:
        return "我没有在题库里找到足够相关的题目。你可以换一个更具体的关键词，例如“牛顿第二定律”“闭合电路欧姆定律”或“电磁感应实验”。"

    lines = [
        f"我根据你的问题“{user_text}”从题库里找到了 {len(context)} 道可参考题。",
        "",
        "可以优先关注这些题：",
    ]
    for question in context[:5]:
        desc = " / ".join(
            part
            for part in [question.question_type, question.knowledge_point, f"难度 {question.difficulty}" if question.difficulty else None]
            if part
        )
        lines.append(f"- {question.question_id}：{question.title}（{desc or '未标注'}）")

    if suggestions:
        lines.extend(["", "组卷建议："])
        for suggestion in suggestions:
            lines.append(
                f"- {suggestion.title}：{suggestion.rationale} 建议题目 {len(suggestion.question_ids)} 道，约 {suggestion.estimated_score} 分。"
            )

    return "\n".join(lines)


def _build_model_messages(
    request: AiAssistantChatRequest,
    context: list[AiAssistantQuestionContext],
    suggestions: list[CompositionSuggestion],
) -> list[dict[str, str]]:
    context_text = "\n".join(
        f"{idx + 1}. {q.question_id} | {q.question_type or '题型未标注'} | 难度 {q.difficulty or '未标注'} | "
        f"{q.knowledge_point or '知识点未标注'} | {q.title} | 答案: {q.answer or '无'}"
        for idx, q in enumerate(context)
    )
    suggestion_text = "\n".join(
        f"- {s.title}: {s.rationale}; 题目: {', '.join(s.question_ids)}; 估分: {s.estimated_score}"
        for s in suggestions
    )
    system = f"""你是 Physics Vault 的题库备课助手。你必须基于下方数据库检索到的题目上下文回答。

回答要求：
1. 用中文，面向高中物理老师。
2. 如果用户问题目、知识点、解析或组卷，引用题目 ID。
3. 给出可执行的组卷建议，包括题目选择顺序、难度搭配、是否适合作为课堂练习/作业/小测。
4. 不要声称题库中存在上下文以外的具体题目。

数据库题目上下文：
{context_text or "本次没有检索到题目。"}

系统生成的候选组卷方案：
{suggestion_text or "暂无。"}
"""
    messages = [{"role": "system", "content": system}]
    for message in request.messages[-10:]:
        if message.role == "system":
            continue
        messages.append({"role": message.role, "content": message.content})
    return messages
