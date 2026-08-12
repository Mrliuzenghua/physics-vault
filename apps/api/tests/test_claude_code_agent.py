import asyncio
import json
import sqlite3
import subprocess
from pathlib import Path
from uuid import uuid4

from physics_vault_api.schemas.agents import AgentConfig, QuestionPickerAgentRequest
from physics_vault_api.schemas.ai_assistant import AiAssistantMessage
from physics_vault_api.services import claude_code_agent as agent_module
from physics_vault_api.services.ai_assistant import _candidate_query_tokens
from physics_vault_api.services.claude_code_agent import (
    ClaudeCodeAgentService,
    _build_question_picker_prompt,
    _clean_latex_in_value,
    _clean_review_task_latex_artifacts,
    _extract_agent_json,
    _fallback_resume_mode,
    _is_direct_review_latex_cleanup_request,
    _load_config,
    _save_config,
)


class FakeQuestionSearchRepository:
    def search_questions(self, **_kwargs):
        return [
            {
                "question_id": "q-001",
                "title": "牛顿第二定律基础选择题",
                "question_type": "single_choice",
                "difficulty": 1,
                "topic3": "牛顿第二定律",
                "source": "单元练习",
                "answer": "A",
                "analysis": "由 F=ma 判断。",
                "tags": ["力学", "基础"],
            },
            {
                "question_id": "q-002",
                "title": "加速度与合力计算题",
                "question_type": "calculation",
                "difficulty": 2,
                "topic3": "牛顿第二定律",
                "source": "课堂例题",
            },
        ], 2


class EmptyThenBrowseRepository:
    def __init__(self):
        self.queries = []

    def search_questions(self, **kwargs):
        self.queries.append(kwargs.get("query"))
        if kwargs.get("query") is None:
            return [
                {
                    "question_id": "browse-001",
                    "title": "浏览兜底题",
                    "question_type": "single_choice",
                    "difficulty": 1,
                }
            ], 1
        return [], 0


class TrackingRepository(FakeQuestionSearchRepository):
    def __init__(self):
        self.search_calls = 0

    def search_questions(self, **kwargs):
        self.search_calls += 1
        return super().search_questions(**kwargs)


def test_candidate_query_tokens_expand_physics_tags():
    tokens = _candidate_query_tokens("帮我找一个考氢原子能级的题目")

    assert tokens[:3] == ["氢原子能级", "氢原子", "能级跃迁"]
    assert "能级" in tokens


def test_targeted_search_does_not_fallback_to_browse_results():
    service = ClaudeCodeAgentService(EmptyThenBrowseRepository())

    context = service._search_context("帮我找一个考氢原子能级的题目", 12)

    assert context == []
    assert None not in service._repo.queries


def test_agent_config_round_trips(monkeypatch):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)

    _save_config(AgentConfig(claude_code_path="claude.cmd", enabled=True, timeout_seconds=120))

    loaded = _load_config()
    assert loaded.claude_code_path == "claude.cmd"
    assert loaded.enabled is True
    assert loaded.timeout_seconds == 120


def test_extract_agent_json_accepts_markdown_wrapped_json():
    parsed = _extract_agent_json(
        """```json
        {"reply": "建议先讲基础题", "question_ids": ["q-001"]}
        ```"""
    )

    assert parsed["reply"] == "建议先讲基础题"
    assert parsed["question_ids"] == ["q-001"]


def test_session_fallback_modes():
    assert _fallback_resume_mode("Error: No conversation found with session ID: abc", True) is False
    assert _fallback_resume_mode("Error: Session ID abc is already in use.", False) is True
    assert _fallback_resume_mode("Other error", True) is None


def test_print_mode_passes_scoped_mcp_permissions(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(agent_module, "_resolve_executable", lambda _path: "claude")
    monkeypatch.setattr(agent_module, "_mcp_config_path", lambda: tmp_path / ".mcp.json")
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        agent_module.subprocess,
        "run",
        lambda args, **_kwargs: captured.setdefault("result", subprocess.CompletedProcess(args, 0, "OK", "")),
    )

    result = agent_module._run_claude_print(
        AgentConfig(claude_code_path="claude", enabled=True, timeout_seconds=30),
        "清空组卷工作台",
    )

    args = captured["result"].args
    assert result == "OK"
    assert "--mcp-config" in args
    assert "--allowedTools" in args
    assert "mcp__physics_vault__get_composition_workbench" in args
    assert "mcp__physics_vault__remove_items_from_composition_workbench" in args


def test_question_picker_falls_back_when_claude_disabled(monkeypatch):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)
    _save_config(AgentConfig(claude_code_path="", enabled=False, timeout_seconds=90))

    service = ClaudeCodeAgentService(FakeQuestionSearchRepository())
    response = asyncio.run(
        service.pick_questions(
            QuestionPickerAgentRequest(
                messages=[
                    AiAssistantMessage(
                        role="user",
                        content="帮我找两道牛顿第二定律题，适合课堂例题。",
                    )
                ],
                context_limit=5,
            )
        )
    )

    assert response.agent_used is False
    assert response.agent_name == "rule-based"
    assert [question.question_id for question in response.selected_questions] == ["q-001", "q-002"]
    assert response.actions[0].type == "add_to_basket"
    assert response.actions[0].question_ids == ["q-001", "q-002"]
    assert "Claude Code 智能体未启用" in response.warnings[0]
    assert response.session_id
    assert [step.title for step in response.trace] == [
        "读取对话目标",
        "复用对话缓存",
        "检索数据库题目",
        "使用规则选题",
    ]


def test_question_picker_lets_claude_decide_whether_to_search(monkeypatch):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)
    _save_config(AgentConfig(claude_code_path="claude.cmd", enabled=True, timeout_seconds=90))
    monkeypatch.setattr(agent_module, "_check_claude_code", lambda _config: (True, "ok", "test"))

    async def fake_run_claude_print_stream(_config, prompt, **_kwargs):
        assert "固定上下文题 JSON" in prompt
        yield '{"reply":"已判断本轮无需预置候选题。","question_ids":[]}'

    monkeypatch.setattr(agent_module, "_run_claude_print_stream", fake_run_claude_print_stream)

    repo = TrackingRepository()
    service = ClaudeCodeAgentService(repo)
    response = asyncio.run(
        service.pick_questions(
            QuestionPickerAgentRequest(
                messages=[AiAssistantMessage(role="user", content="帮我找匀变速直线运动题")],
                context_limit=5,
            )
        )
    )

    assert response.agent_used is True
    assert repo.search_calls == 0
    assert [step.title for step in response.trace][:3] == [
        "读取对话目标",
        "复用对话缓存",
        "交给 Claude 判断查库",
    ]


def test_casual_greeting_does_not_call_claude_or_search(monkeypatch):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)
    _save_config(AgentConfig(claude_code_path="claude.cmd", enabled=True, timeout_seconds=90))
    monkeypatch.setattr(agent_module, "_check_claude_code", lambda _config: (True, "ok", "test"))
    called = {"claude": 0}

    async def fake_run_claude_print_stream(_config, _prompt, **_kwargs):
        called["claude"] += 1
        yield '{"reply":"should not happen","question_ids":[]}'

    monkeypatch.setattr(agent_module, "_run_claude_print_stream", fake_run_claude_print_stream)

    repo = TrackingRepository()
    service = ClaudeCodeAgentService(repo)
    response = asyncio.run(
        service.pick_questions(
            QuestionPickerAgentRequest(
                messages=[AiAssistantMessage(role="user", content="你好")],
                context_limit=5,
            )
        )
    )

    assert called["claude"] == 0
    assert repo.search_calls == 0
    assert response.selected_questions == []
    assert "你好" in response.reply
    assert [step.title for step in response.trace] == [
        "读取对话目标",
        "复用对话缓存",
        "识别普通对话",
    ]


def test_question_picker_prompt_keeps_page_context_separate():
    request = QuestionPickerAgentRequest(
        messages=[
            *[
                AiAssistantMessage(role="assistant", content=f"历史回复 {index}")
                for index in range(12)
            ],
            AiAssistantMessage(
                role="system",
                content="当前页面：校对中心任务页 /review/task-123\n当前校对任务 task_id：task-123",
            ),
            AiAssistantMessage(role="user", content="你能读取当前校对中心的题目吗"),
        ],
        context_limit=5,
    )

    prompt = _build_question_picker_prompt(request, [])

    assert "当前页面上下文：" in prompt
    assert "当前校对任务 task_id：task-123" in prompt
    assert "不能让老师自行处理" in prompt
    assert "行内公式统一为 $...$" in prompt


def test_review_center_request_does_not_fallback_to_formal_question_search(monkeypatch, tmp_path):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)
    monkeypatch.setattr(agent_module, "default_db_path", lambda: tmp_path / "missing.sqlite3")
    _save_config(AgentConfig(claude_code_path="claude.cmd", enabled=True, timeout_seconds=90))
    monkeypatch.setattr(agent_module, "_check_claude_code", lambda _config: (True, "ok", "test"))

    async def fake_run_claude_print_stream(_config, _prompt, **_kwargs):
        raise TimeoutError("Claude Code 调用超过 90 秒")
        yield ""  # pragma: no cover

    monkeypatch.setattr(agent_module, "_run_claude_print_stream", fake_run_claude_print_stream)

    repo = TrackingRepository()
    service = ClaudeCodeAgentService(repo)
    response = asyncio.run(
        service.pick_questions(
            QuestionPickerAgentRequest(
                messages=[AiAssistantMessage(role="user", content="帮我清洗一下校对中心的题目")],
                context_limit=5,
            )
        )
    )

    assert repo.search_calls == 0
    assert response.selected_questions == []
    assert response.actions == []
    assert "校对中心清洗任务" in response.reply
    assert response.warnings == []


def test_risk_repair_request_is_routed_to_review_center(monkeypatch, tmp_path):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)
    monkeypatch.setattr(agent_module, "default_db_path", lambda: tmp_path / "missing.sqlite3")
    _save_config(AgentConfig(claude_code_path="claude.cmd", enabled=True, timeout_seconds=90))
    monkeypatch.setattr(agent_module, "_check_claude_code", lambda _config: (True, "ok", "test"))

    async def fake_run_claude_print_stream(_config, _prompt, **_kwargs):
        raise TimeoutError("timeout")
        yield ""  # pragma: no cover

    monkeypatch.setattr(agent_module, "_run_claude_print_stream", fake_run_claude_print_stream)

    repo = TrackingRepository()
    response = asyncio.run(
        ClaudeCodeAgentService(repo).pick_questions(
            QuestionPickerAgentRequest(messages=[AiAssistantMessage(role="user", content="帮我修复检验页的全部风险")])
        )
    )

    assert repo.search_calls == 0
    assert response.selected_questions == []


def test_review_center_timeout_reads_current_task_directly(monkeypatch, tmp_path):
    config_path = Path(".codex-run") / f"agent-config-{uuid4().hex}.json"
    db_path = tmp_path / "physics.sqlite3"
    monkeypatch.setattr(agent_module, "_CONFIG_FILE", config_path)
    monkeypatch.setattr(agent_module, "default_db_path", lambda: db_path)
    _save_config(AgentConfig(claude_code_path="claude.cmd", enabled=True, timeout_seconds=90))
    monkeypatch.setattr(agent_module, "_check_claude_code", lambda _config: (True, "ok", "test"))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE import_pipeline_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                input_summary_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO import_pipeline_tasks (
                task_id, task_type, status, created_at, updated_at, input_summary_json, result_json, error
            ) VALUES (?, 'import_confirmed', 'completed', 'now', 'now', ?, ?, NULL)
            """,
            (
                "task-current-123",
                json.dumps({"batch_id": "batch-1", "question_count": 1}, ensure_ascii=False),
                json.dumps(
                    {
                        "batch_id": "batch-1",
                        "question_count": 1,
                        "questions": [{"question_id": "draft-1", "title": "当前校对题"}],
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    async def fake_run_claude_print_stream(_config, _prompt, **_kwargs):
        raise TimeoutError("Claude Code 调用超过 90 秒")
        yield ""  # pragma: no cover

    monkeypatch.setattr(agent_module, "_run_claude_print_stream", fake_run_claude_print_stream)

    service = ClaudeCodeAgentService(TrackingRepository())
    response = asyncio.run(
        service.pick_questions(
            QuestionPickerAgentRequest(
                messages=[
                    AiAssistantMessage(
                        role="system",
                        content="当前页面：校对中心任务页 /review/task-current-123\n当前校对任务 task_id：task-current-123",
                    ),
                    AiAssistantMessage(role="user", content="你能读取校对中心的题目吗"),
                ],
                context_limit=5,
            )
        )
    )

    assert response.warnings == []
    assert "能读" in response.reply
    assert "draft-1" in response.reply
    assert "不是空的" in response.reply


def test_direct_review_latex_cleanup_updates_task_result(monkeypatch, tmp_path):
    db_path = tmp_path / "review.sqlite3"
    monkeypatch.setattr(agent_module, "default_review_db_path", lambda: db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE import_pipeline_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                input_summary_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO import_pipeline_tasks (
                task_id, task_type, status, created_at, updated_at, input_summary_json, result_json, error
            ) VALUES ('task-latex', 'import_confirmed', 'completed', 'now', 'now', '{}', ?, NULL)
            """,
            (
                json.dumps(
                    {
                        "questions": [
                            {
                                "question_id": "q-1",
                                "title": "探究加速度*a*与质量*m*的关系",
                                "analysis": "其中*M*不变，*mg*偏差增大，结论$F=ma$。",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    result = _clean_review_task_latex_artifacts("task-latex")

    assert result["ok"] is True
    assert result["changed_questions"] == 1
    assert result["replacement_count"] == 4
    with sqlite3.connect(db_path) as conn:
        raw = conn.execute("SELECT result_json FROM import_pipeline_tasks WHERE task_id='task-latex'").fetchone()[0]
    saved = json.loads(raw)
    question = saved["questions"][0]
    assert "加速度$a$与质量$m$" in question["title"]
    assert "其中$M$不变，$mg$偏差增大" in question["analysis"]


def test_latex_cleanup_normalizes_ocr_dash_table():
    raw = """------------------------- ------------------------------------------------------------------
$\\frac{m}{\\text{kg}}$ $\\frac{a}{\\left( \\text{m} \\cdot \\text{s}^{\\text{-2}} \\right)}$

0.2 0.618

0.33 0.482

0.40 0.403

0.50 0.317

1.00 0.152
------------------------- ------------------------------------------------------------------"""

    cleaned, replacements = _clean_latex_in_value(raw, key="stem")

    assert replacements == 1
    assert "| $\\frac{m}{\\text{kg}}$ | $\\frac{a}{\\left( \\text{m} \\cdot \\text{s}^{\\text{-2}} \\right)}$ |" in cleaned
    assert "| --- | --- |" in cleaned
    assert "| 0.2 | 0.618 |" in cleaned
    assert "| 1.00 | 0.152 |" in cleaned
    assert "-------------------------" not in cleaned


def test_latex_cleanup_preserves_balanced_display_math_and_repairs_mixed_delimiters():
    raw = {
        "title": "能量关系为 $$E=mc^{2}$$。",
        "analysis": "$$E=6.6 \\times 10^{-34}\\text{ J}$",
    }

    cleaned, replacements = _clean_latex_in_value(raw)

    assert cleaned["title"] == "能量关系为 $E=mc^{2}$。"
    assert cleaned["analysis"] == "$$E=6.6 \\times 10^{-34}\\text{ J}$$"
    assert replacements == 2


def test_direct_review_latex_cleanup_request_matches_current_page_context():
    request = QuestionPickerAgentRequest(
        messages=[
            {
                "role": "system",
                "content": (
                    "当前页面：校对中心任务页 /review/60a869a8-2090-47b8-9adb-64aec7b53c5c\n"
                    "当前校对任务 task_id：60a869a8-2090-47b8-9adb-64aec7b53c5c"
                ),
            },
            {
                "role": "assistant",
                "content": "我发现当前校对任务里有些题的 LaTeX 公式格式需要清洗，例如加速度*a*与质量*m*。",
            },
            {"role": "user", "content": "帮我直接在这个数据库里修改"},
        ]
    )

    assert _is_direct_review_latex_cleanup_request(request, "帮我直接在这个数据库里修改") is True


def test_direct_review_latex_cleanup_accepts_draft_execution_wording():
    request = QuestionPickerAgentRequest(
        messages=[
            {
                "role": "system",
                "content": "当前页面：校对中心任务页 /review/task-current-123\n当前校对任务 task_id：task-current-123",
            },
            {
                "role": "assistant",
                "content": "发现题干里的 LaTeX 格式需要清洗，例如速度*v*。",
            },
            {"role": "user", "content": "直接在草稿单修改执行"},
        ]
    )

    assert _is_direct_review_latex_cleanup_request(request, "直接在草稿单修改执行") is True
