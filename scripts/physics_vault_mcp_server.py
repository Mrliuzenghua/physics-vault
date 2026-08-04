from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))
PYDEPS = ROOT / ".codex-run" / "pydeps"
PYWIN32 = PYDEPS / "win32"
PYWIN32_LIB = PYDEPS / "win32" / "lib"
PYWIN32_SYSTEM32 = PYDEPS / "pywin32_system32"
if PYWIN32.exists() and str(PYWIN32) not in sys.path:
    sys.path.insert(0, str(PYWIN32))
if PYWIN32_LIB.exists() and str(PYWIN32_LIB) not in sys.path:
    sys.path.insert(0, str(PYWIN32_LIB))
if PYWIN32_SYSTEM32.exists() and hasattr(os, "add_dll_directory"):
    os.add_dll_directory(str(PYWIN32_SYSTEM32))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from physics_vault_api.paths import default_db_path, default_review_db_path  # noqa: E402
from physics_vault_api.repositories.import_tasks import SQLiteImportTaskRepository  # noqa: E402
from physics_vault_api.schemas.paper_drafts import PaperDraftItem, PaperDraftUpsertRequest  # noqa: E402
from physics_vault_api.schemas.question_search import BatchQuestionFetchRequest, QuestionSearchParams  # noqa: E402
from physics_vault_api.services.document_pipeline import (  # noqa: E402
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
)
from physics_vault_api.services.lesson_exports import LessonExportService  # noqa: E402
from physics_vault_api.services.ai_assistant import _candidate_query_tokens  # noqa: E402
from physics_vault_api.services.change_audit import ChangeAuditService  # noqa: E402
from physics_vault_api.services.metadata_management import MetadataManagementService  # noqa: E402
from physics_vault_api.services.math_text import normalize_math_delimiters  # noqa: E402
from physics_vault_api.services.question_search import QuestionSearchService  # noqa: E402
from physics_vault_api.services.paper_drafts import PaperDraftService  # noqa: E402
from physics_vault_api.services.similar_questions import SimilarQuestionsService  # noqa: E402
from physics_vault_api.services.task_center import TaskActionContext, TaskCenterService  # noqa: E402

server = MCPServer(
    name="physics_vault",
    title="Physics Vault Database",
    version="0.2.0",
    instructions=(
        "Use these tools to inspect the local high-school physics question bank. "
        "Canonical question content is read-only; searchable metadata may be maintained directly. Review-center tools write only "
        "to the Review DB. submit_ai_generated_review writes review drafts only. "
        "If the user says review center, submitted-for-review, sent for review, draft task, "
        "or asks to clean LaTeX/formulas in reviewed/submitted items, do NOT start with "
        "canonical search_questions/get_questions_by_ids. First call list_review_tasks or "
        "get_review_task on the Review DB, then clean_review_task_latex if needed. "
        "Use list_review_queue/list_review_tasks/get_review_task for fast review-center discovery. "
        "When the user asks to import every Word file from a folder into the review center, use "
        "import_word_folder_to_review: first dry_run=true to show the file plan, then dry_run=false "
        "only after the user confirms the folder and count. This workflow writes only the Review DB. "
        "Use get_review_task_full when the complete draft is needed. "
        "Use database_boundary_report when unsure which database/tool family to use. "
        "Use clean_review_task_latex/update_review_task_draft to modify the current draft in place; "
        "do not create a duplicate task with submit_ai_generated_review. "
        "Composition-workbench tools manage only paper_drafts and paper_draft_items: they may add "
        "canonical question references, standard knowledge-point cards, teaching text/title blocks, or "
        "change their order. They never alter a canonical question or knowledge point. This is a free-form "
        "workspace: execute directly when the teacher explicitly requests an edit; use dry_run=true only when a preview is requested. "
        "Use create_knowledge_points and batch_update_question_metadata directly to normalize tags, "
        "knowledge bindings, difficulty, question type, and normalized source without asking for approval. "
        "These metadata tools cannot change stems, options, answers, analysis, images, or publication status. "
        "return_question_to_review remains a controlled canonical content workflow and requires preview plus confirmation. "
        "Legacy batch_replace_question_tags and batch_replace_question_knowledge_points remain available for compatibility. "
        "Use list_change_batches/get_change_batch/rollback_change_batch to inspect or roll back audited changes. "
        "Task status tools are read-only. retry_job and cancel_job require confirmed=true after explicit human confirmation. "
        "Task write tools call the application task service and record source, session, operator, and an audit id."
    ),
)


def _search_service() -> QuestionSearchService:
    return QuestionSearchService()


def _import_service() -> ImportPipelineService:
    return ImportPipelineService(
        task_repo=SQLiteImportTaskRepository(str(_review_db_path())),
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
    )


def _task_center_service() -> TaskCenterService:
    import_service = _import_service()
    return TaskCenterService(
        import_service,
        lesson_export_service=LessonExportService(import_service._task_repo),
    )


def _paper_draft_service() -> PaperDraftService:
    return PaperDraftService()


def _change_audit_service() -> ChangeAuditService:
    return ChangeAuditService(
        db_path=_formal_db_path(),
        review_db_path=_review_db_path(),
    )


def _metadata_management_service() -> MetadataManagementService:
    return MetadataManagementService(_formal_db_path())


def _formal_db_path() -> Path:
    return default_db_path()


def _review_db_path() -> Path:
    review_path = default_review_db_path()
    review_path.parent.mkdir(parents=True, exist_ok=True)
    return review_path


def _connect_formal_read_db() -> sqlite3.Connection:
    db_path = _formal_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _connect_formal_write_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_formal_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _connect_review_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_review_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_review_db_schema(conn)
    return conn


def _ensure_review_db_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_pipeline_tasks (
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
        CREATE INDEX IF NOT EXISTS idx_import_pipeline_tasks_work
        ON import_pipeline_tasks(task_type, status, updated_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_queue (
            review_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL DEFAULT 'question',
            entity_id TEXT NOT NULL,
            queue_type TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            payload_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_queue_work
        ON review_queue(status, queue_type, priority, updated_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_workspace_ignored_sessions (
            session_id TEXT PRIMARY KEY,
            ignored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _ensure_change_audit_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS change_batches (
            batch_id TEXT PRIMARY KEY,
            change_type TEXT NOT NULL,
            reason TEXT,
            source TEXT NOT NULL DEFAULT 'physics_vault_mcp',
            status TEXT NOT NULL DEFAULT 'applied',
            target_count INTEGER NOT NULL DEFAULT 0,
            changed_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_at TEXT
        )
        """
    )
    for column_sql in [
        "ALTER TABLE change_batches ADD COLUMN rolled_back_at TEXT",
        "ALTER TABLE change_batches ADD COLUMN rollback_reason TEXT",
    ]:
        try:
            conn.execute(column_sql)
        except sqlite3.OperationalError:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS change_items (
            item_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            before_value_json TEXT,
            after_value_json TEXT,
            status TEXT NOT NULL DEFAULT 'changed',
            risk_level TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(batch_id) REFERENCES change_batches(batch_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_change_items_batch
        ON change_items(batch_id, entity_type, entity_id)
        """
    )


def _record_change_batch(
    conn: sqlite3.Connection,
    *,
    change_type: str,
    reason: str | None,
    items: list[dict[str, Any]],
    field_name: str,
    risk_level: str,
) -> str:
    _ensure_change_audit_schema(conn)
    batch_id = f"CHG-{_short_id()}"
    changed_items = [item for item in items if item.get("status") == "changed"]
    conn.execute(
        """
        INSERT INTO change_batches (
            batch_id, change_type, reason, target_count, changed_count, applied_at
        ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (batch_id, change_type, reason, len(items), len(changed_items)),
    )
    for item in changed_items:
        conn.execute(
            """
            INSERT INTO change_items (
                item_id, batch_id, entity_type, entity_id, field_name,
                before_value_json, after_value_json, status, risk_level
            ) VALUES (?, ?, 'question', ?, ?, ?, ?, 'changed', ?)
            """,
            (
                f"CHI-{_short_id()}",
                batch_id,
                item["question_id"],
                field_name,
                json.dumps(item.get("before_value"), ensure_ascii=False),
                json.dumps(item.get("after_value"), ensure_ascii=False),
                risk_level,
            ),
        )
    return batch_id


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump_model(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump_model(item) for key, item in value.items()}
    return value


def _clean_args(args: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in args.items() if value not in (None, "")}


def _tool_error(
    code: str,
    message: str,
    *,
    field: str | None = None,
    retryable: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Return one stable MCP error shape while keeping the legacy text field."""
    details = {"field": field} if field else {}
    return {
        "ok": False,
        "error": message,
        "error_info": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details,
        },
        **extra,
    }


_REVIEW_INTENT_RE = re.compile(
    r"(校对中心|待校对|审核任务|审核队列|送审|已送审|草稿|回炉|复核|review center|submitted|draft)",
    re.IGNORECASE,
)
_FORMAL_INTENT_RE = re.compile(r"(正式库|正式题库|标准库|已入库|canonical|approved)", re.IGNORECASE)


def _looks_like_review_intent(text: str | None) -> bool:
    value = str(text or "")
    return bool(_REVIEW_INTENT_RE.search(value)) and not bool(_FORMAL_INTENT_RE.search(value))


@server.tool()
def list_filter_facets() -> dict[str, Any]:
    """列出题库可用筛选项，包括年份、模块、题型、难度、状态和知识点层级取值。"""
    return _dump_model(_search_service().get_facets())


@server.tool()
def search_questions(
    query: str | None = None,
    search_mode: Literal["browse", "strict", "hybrid", "similar"] = "strict",
    question_type: str | None = None,
    difficulty: str | None = None,
    status: str | None = None,
    year: int | None = None,
    module: str | None = None,
    topic1_id: str | None = None,
    topic2_id: str | None = None,
    topic3_id: str | None = None,
    topic2: str | None = None,
    topic3: str | None = None,
    region: str | None = None,
    exam_type: str | None = None,
    has_media: bool | None = None,
    image_count_min: int = 0,
    is_mistake: bool | None = None,
    limit: int = 12,
    offset: int = 0,
) -> dict[str, Any]:
    """按关键词、题型、难度、知识点、年份、来源等条件检索正式题库。只读。不要用本工具定位送审/校对草稿；那类任务先用 list_review_tasks。"""
    if _looks_like_review_intent(query):
        return {
            "items": [],
            "total": 0,
            "misrouted": True,
            "database_scope": "canonical_read_only",
            "requested_scope": "review_workspace",
            "message": "这个请求看起来是在找送审/校对中心草稿；不要检索正式题库，请改用 list_review_tasks 或 get_review_task。",
            "next_tools": ["list_review_tasks", "get_review_task", "get_review_task_full"],
            "review_database_path": str(_review_db_path()),
            "canonical_database_path": str(_formal_db_path()),
        }
    clean = _clean_args(
        {
            "query": query,
            "search_mode": search_mode,
            "question_type": question_type,
            "difficulty": difficulty,
            "status": status,
            "year": year,
            "module": module,
            "topic1_id": topic1_id,
            "topic2_id": topic2_id,
            "topic3_id": topic3_id,
            "topic2": topic2,
            "topic3": topic3,
            "region": region,
            "exam_type": exam_type,
            "has_media": has_media,
            "image_count_min": image_count_min,
            "is_mistake": is_mistake,
            "limit": min(max(int(limit or 12), 1), 50),
            "offset": max(int(offset or 0), 0),
        }
    )
    if not clean.get("query") and clean.get("search_mode", "strict") != "browse":
        clean["search_mode"] = "browse"
    service = _search_service()
    result = _dump_model(service.search(QuestionSearchParams(**clean)))
    if result.get("items") or not clean.get("query") or clean.get("search_mode") == "browse":
        return result

    tried_terms: list[str] = []
    for term in _candidate_query_tokens(str(clean["query"])):
        if term == clean["query"] or term in tried_terms:
            continue
        tried_terms.append(term)
        expanded = {**clean, "query": term, "search_mode": "strict"}
        result = _dump_model(service.search(QuestionSearchParams(**expanded)))
        result["expanded_from"] = clean["query"]
        result["query_used"] = term
        result["tried_terms"] = tried_terms
        if result.get("items"):
            return result

    result["expanded_from"] = clean["query"]
    result["tried_terms"] = tried_terms
    return result


@server.tool()
def get_questions_by_ids(question_ids: list[str]) -> dict[str, Any]:
    """按题号批量读取正式题库题目详情。只读。"""
    normalized_ids = list(dict.fromkeys(str(item).strip() for item in question_ids if str(item).strip()))
    if not normalized_ids:
        return _tool_error("INVALID_ARGUMENT", "question_ids 至少需要一个有效题号。", field="question_ids")
    if len(normalized_ids) > 50:
        return _tool_error(
            "LIMIT_EXCEEDED",
            "一次最多读取 50 道题，请分批调用。",
            field="question_ids",
            requested_count=len(normalized_ids),
            max_count=50,
        )
    return _dump_model(_search_service().get_by_ids(BatchQuestionFetchRequest(question_ids=normalized_ids)))


def _get_compose_draft_or_error(draft_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    service = _paper_draft_service()
    requested_id = str(draft_id or "").strip()
    try:
        draft = service.get(requested_id) if requested_id else service.get_latest()
    except ValueError:
        return None, _tool_error(
            "DRAFT_NOT_FOUND",
            f"组卷工作台草稿不存在：{requested_id}。",
            field="draft_id",
            draft_id=requested_id,
            next_tools=["list_composition_workbenches", "create_composition_workbench"],
        )
    if draft is None:
        return None, _tool_error(
            "DRAFT_NOT_FOUND",
            "尚未创建组卷工作台草稿。请先调用 create_composition_workbench。",
            next_tools=["create_composition_workbench", "list_composition_workbenches"],
        )
    return _dump_model(draft), None


def _compose_draft_preview(draft: dict[str, Any], items: list[dict[str, Any]], *, action: str) -> dict[str, Any]:
    question_count = sum(1 for item in items if item.get("type") == "question")
    return {
        "ok": True,
        "dry_run": True,
        "action": action,
        "draft_id": draft["id"],
        "draft_title": draft["title"],
        "before": {"item_count": len(draft.get("items") or []), "question_count": draft.get("question_count", 0)},
        "after": {"item_count": len(items), "question_count": question_count},
        "items": [
            {"id": item["id"], "type": item["type"], "position": index, "title": item.get("title")}
            for index, item in enumerate(items)
        ],
        "message": "这是组卷工作台草稿的预览；不会修改正式题库或标准知识库。确认后以 dry_run=false 执行。",
    }


def _save_compose_draft(draft: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    request = PaperDraftUpsertRequest(
        id=draft["id"],
        title=draft["title"],
        subtitle=draft.get("subtitle"),
        source=draft.get("source") or "ai",
        status=draft.get("status") or "draft",
        items=[PaperDraftItem(**{**item, "position": index}) for index, item in enumerate(items)],
        metadata=draft.get("metadata") or {},
        quality_report=draft.get("quality_report") or {},
    )
    return _dump_model(_paper_draft_service().save(request))


def _compose_insert_position(items: list[dict[str, Any]], insert_at: int | None) -> int:
    if insert_at is None:
        return len(items)
    return min(max(int(insert_at), 0), len(items))


def _teaching_points(topic_name: str) -> list[str]:
    return [
        f"概念与条件：明确“{topic_name}”的研究对象、过程、适用条件和核心物理量。",
        "规律与表达：写出关键关系式，并结合图像、实验现象或能量变化解释物理意义。",
        "解题路径：先识别模型，再列关系式与边界条件，最后检查方向、单位与数量级。",
        "常见误区：警惕条件变化、正负号、临界状态，以及过程量与状态量的混淆。",
    ]


@server.tool()
def list_composition_workbenches(limit: int = 20) -> dict[str, Any]:
    """列出已保存的组卷工作台草稿。只读；草稿不会修改正式题库。"""
    result = _paper_draft_service().list(limit=min(max(int(limit or 20), 1), 100))
    return {"ok": True, "items": _dump_model(result).get("items", []), "database_scope": "composition_workspace"}


@server.tool()
def get_composition_workbench(draft_id: str | None = None) -> dict[str, Any]:
    """读取一份组卷工作台草稿；不传 draft_id 时读取最近编辑的一份。只读。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    return {"ok": True, "database_scope": "composition_workspace", "draft": draft}


@server.tool()
def create_composition_workbench(
    title: str,
    subtitle: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """新建空的组卷工作台草稿。默认只预览；dry_run=false 才会保存。"""
    clean_title = str(title or "").strip()
    if not clean_title:
        return {"ok": False, "error": "组卷工作台标题不能为空。"}
    proposed_id = f"draft-{_short_id()}"
    preview = {
        "ok": True,
        "dry_run": bool(dry_run),
        "action": "create_composition_workbench",
        "draft_id": proposed_id,
        "draft_title": clean_title,
        "subtitle": str(subtitle or "").strip() or None,
        "message": "这是独立的组卷草稿，不会新增或修改正式题库题目、知识点。",
    }
    if dry_run:
        preview["message"] += " 确认后以 dry_run=false 创建。"
        return preview
    saved = _dump_model(
        _paper_draft_service().save(
            PaperDraftUpsertRequest(
                id=proposed_id,
                title=clean_title,
                subtitle=str(subtitle or "").strip() or None,
                source="ai",
                status="draft",
                items=[],
                metadata={"created_by": "physics_vault_mcp"},
            )
        )
    )
    return {"ok": True, "dry_run": False, "action": "create_composition_workbench", "draft": saved}


@server.tool()
def add_questions_to_composition_workbench(
    question_ids: list[str],
    draft_id: str | None = None,
    insert_at: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把正式题库中的题号引用加入组卷工作台。仅写草稿，不会修改题库题目。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    requested_ids = list(dict.fromkeys(str(item).strip() for item in question_ids if str(item).strip()))[:50]
    if not requested_ids:
        return {"ok": False, "error": "至少提供一个正式题库 question_id。"}
    summaries = _fetch_formal_question_summaries(requested_ids)
    missing = [qid for qid in requested_ids if qid not in summaries]
    existing_ids = {str(item.get("question_id") or "") for item in draft.get("items") or [] if item.get("type") == "question"}
    added = [qid for qid in requested_ids if qid in summaries and qid not in existing_ids]
    skipped = [qid for qid in requested_ids if qid in existing_ids]
    new_items = [
        {
            "id": f"compose-question-{_short_id()}",
            "type": "question",
            "position": 0,
            "question_id": qid,
            "title": summaries[qid]["title"] or qid,
            "score": None,
            "payload": summaries[qid],
        }
        for qid in added
    ]
    items = list(draft.get("items") or [])
    position = _compose_insert_position(items, insert_at)
    next_items = [*items[:position], *new_items, *items[position:]]
    if dry_run:
        preview = _compose_draft_preview(draft, next_items, action="add_questions")
        preview.update({"added_question_ids": added, "missing_question_ids": missing, "already_present_question_ids": skipped})
        return preview
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "add_questions", "draft": saved, "added_question_ids": added, "missing_question_ids": missing, "already_present_question_ids": skipped}


@server.tool()
def add_knowledge_to_composition_workbench(
    topic3_ids: list[str],
    draft_id: str | None = None,
    insert_at: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把标准三级知识点加入组卷工作台，作为可展示的教学知识卡。仅写草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    requested_ids = list(dict.fromkeys(str(item).strip() for item in topic3_ids if str(item).strip()))[:50]
    if not requested_ids:
        return {"ok": False, "error": "至少提供一个标准知识点 topic3_id。"}
    with _connect_formal_read_db() as conn:
        topics = _fetch_topics(conn, requested_ids)
    existing_topic_ids = {
        str((item.get("payload") or {}).get("topic3_id") or (item.get("payload") or {}).get("id") or "")
        for item in draft.get("items") or []
        if item.get("type") == "knowledge"
    }
    added = [topic_id for topic_id in requested_ids if topic_id in topics and topic_id not in existing_topic_ids]
    missing = [topic_id for topic_id in requested_ids if topic_id not in topics]
    skipped = [topic_id for topic_id in requested_ids if topic_id in existing_topic_ids]
    new_items = []
    for topic_id in added:
        topic = _topic_payload(topics[topic_id])
        display_title = f"{topic['topic2_name']}：{topic['topic3_name']}"
        new_items.append(
            {
                "id": f"compose-knowledge-{_short_id()}",
                "type": "knowledge",
                "position": 0,
                "title": display_title,
                "payload": {
                    "id": topic_id,
                    "topic3_id": topic_id,
                    "title": display_title,
                    "summary": f"{topic['topic1_name']} / {topic['topic2_name']}",
                    "points": _teaching_points(topic['topic3_name']),
                    "relatedQuestionIds": [],
                    **topic,
                },
            }
        )
    items = list(draft.get("items") or [])
    position = _compose_insert_position(items, insert_at)
    next_items = [*items[:position], *new_items, *items[position:]]
    if dry_run:
        preview = _compose_draft_preview(draft, next_items, action="add_knowledge")
        preview.update({"added_topic3_ids": added, "missing_topic3_ids": missing, "already_present_topic3_ids": skipped})
        return preview
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "add_knowledge", "draft": saved, "added_topic3_ids": added, "missing_topic3_ids": missing, "already_present_topic3_ids": skipped}


@server.tool()
def insert_teaching_block_to_composition_workbench(
    title: str,
    content: str = "",
    block_kind: Literal["body", "exam_title", "name_line", "section_title", "text_box"] = "body",
    draft_id: str | None = None,
    insert_at: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """在组卷工作台插入教学对象：试卷标题、分节标题、姓名栏或普通说明文字。仅写草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    clean_title = str(title or "").strip()
    if not clean_title:
        return {"ok": False, "error": "教学对象标题不能为空。"}
    item = {
        "id": f"compose-text-{_short_id()}",
        "type": "text",
        "position": 0,
        "title": clean_title,
        "payload": {"id": f"text-{_short_id()}", "title": clean_title, "content": str(content or ""), "blockKind": block_kind},
    }
    items = list(draft.get("items") or [])
    position = _compose_insert_position(items, insert_at)
    next_items = [*items[:position], item, *items[position:]]
    if dry_run:
        return _compose_draft_preview(draft, next_items, action="insert_teaching_block")
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "insert_teaching_block", "draft": saved, "inserted_item_id": item["id"]}


@server.tool()
def reorder_composition_workbench(
    ordered_item_ids: list[str],
    draft_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """按完整 item id 列表调整组卷工作台内所有题目、知识卡和教学对象的顺序。仅写草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    items = list(draft.get("items") or [])
    current_ids = [str(item.get("id") or "") for item in items]
    requested_ids = [str(item).strip() for item in ordered_item_ids if str(item).strip()]
    if len(requested_ids) != len(items) or set(requested_ids) != set(current_ids):
        return {
            "ok": False,
            "error": "ordered_item_ids 必须恰好包含当前草稿中的每一个 item id 各一次。请先 get_composition_workbench 获取完整顺序。",
            "current_item_ids": current_ids,
        }
    item_map = {str(item["id"]): item for item in items}
    next_items = [item_map[item_id] for item_id in requested_ids]
    if dry_run:
        return _compose_draft_preview(draft, next_items, action="reorder_items")
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "reorder_items", "draft": saved}


@server.tool()
def apply_composition_workbench_plan(
    operations: list[dict[str, Any]],
    draft_id: str | None = None,
    ordered_refs: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """一次完成组卷计划：批量加入题目/知识卡/教学文字并按最终顺序排版。operations 中每项须有唯一 ref 和 kind：question(question_id)、knowledge(topic3_id) 或 text(title/content/block_kind)。ordered_refs 可用 item:<现有item_id> 与各 operation.ref 指定完整最终顺序；省略时按“原有对象 + operations”追加。仅写组卷草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    if not operations or len(operations) > 100:
        return {"ok": False, "error": "operations 必须包含 1 至 100 个操作。"}

    existing_items = list(draft.get("items") or [])
    existing_refs = {f"item:{item['id']}": item for item in existing_items}
    operation_refs: set[str] = set()
    question_requests: list[str] = []
    topic_requests: list[str] = []
    normalized_ops: list[dict[str, Any]] = []
    allowed_block_kinds = {"body", "exam_title", "name_line", "section_title", "text_box"}
    for raw in operations:
        if not isinstance(raw, dict):
            return {"ok": False, "error": "每个 operation 必须是对象。"}
        ref = str(raw.get("ref") or "").strip()
        kind = str(raw.get("kind") or "").strip()
        if not ref or ref in operation_refs or ref in existing_refs:
            return {"ok": False, "error": f"operation ref 必须唯一，且不能与现有 item:<id> 冲突：{ref or '空值'}。"}
        if kind == "question":
            question_id = str(raw.get("question_id") or "").strip()
            if not question_id:
                return {"ok": False, "error": f"{ref} 缺少 question_id。"}
            question_requests.append(question_id)
            normalized_ops.append({"ref": ref, "kind": kind, "question_id": question_id})
        elif kind == "knowledge":
            topic3_id = str(raw.get("topic3_id") or "").strip()
            if not topic3_id:
                return {"ok": False, "error": f"{ref} 缺少 topic3_id。"}
            topic_requests.append(topic3_id)
            normalized_ops.append({"ref": ref, "kind": kind, "topic3_id": topic3_id})
        elif kind == "text":
            title = str(raw.get("title") or "").strip()
            block_kind = str(raw.get("block_kind") or "body")
            if not title or block_kind not in allowed_block_kinds:
                return {"ok": False, "error": f"{ref} 的 text 必须有 title，且 block_kind 必须为 {sorted(allowed_block_kinds)} 之一。"}
            normalized_ops.append({"ref": ref, "kind": kind, "title": title, "content": str(raw.get("content") or ""), "block_kind": block_kind})
        else:
            return {"ok": False, "error": f"{ref} 的 kind 仅支持 question、knowledge、text。"}
        operation_refs.add(ref)

    question_summaries = _fetch_formal_question_summaries(question_requests)
    with _connect_formal_read_db() as conn:
        topics = _fetch_topics(conn, topic_requests)
    existing_question_ids = {str(item.get("question_id") or "") for item in existing_items if item.get("type") == "question"}
    existing_topic_ids = {
        str((item.get("payload") or {}).get("topic3_id") or (item.get("payload") or {}).get("id") or "")
        for item in existing_items if item.get("type") == "knowledge"
    }
    produced: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, str]] = []
    for operation in normalized_ops:
        ref, kind = operation["ref"], operation["kind"]
        if kind == "question":
            question_id = operation["question_id"]
            if question_id not in question_summaries:
                return {"ok": False, "error": f"正式题库不存在 question_id：{question_id}。"}
            if question_id in existing_question_ids:
                skipped.append({"ref": ref, "reason": "question_already_present"})
                continue
            produced[ref] = {"id": f"compose-question-{_short_id()}", "type": "question", "position": 0, "question_id": question_id, "title": question_summaries[question_id]["title"] or question_id, "score": None, "payload": question_summaries[question_id]}
            existing_question_ids.add(question_id)
        elif kind == "knowledge":
            topic3_id = operation["topic3_id"]
            if topic3_id not in topics:
                return {"ok": False, "error": f"标准知识目录不存在 active topic3_id：{topic3_id}。"}
            if topic3_id in existing_topic_ids:
                skipped.append({"ref": ref, "reason": "knowledge_already_present"})
                continue
            topic = _topic_payload(topics[topic3_id])
            title = f"{topic['topic2_name']}：{topic['topic3_name']}"
            produced[ref] = {"id": f"compose-knowledge-{_short_id()}", "type": "knowledge", "position": 0, "title": title, "payload": {"id": topic3_id, "topic3_id": topic3_id, "title": title, "summary": f"{topic['topic1_name']} / {topic['topic2_name']}", "points": _teaching_points(topic['topic3_name']), "relatedQuestionIds": [], **topic}}
            existing_topic_ids.add(topic3_id)
        else:
            produced[ref] = {"id": f"compose-text-{_short_id()}", "type": "text", "position": 0, "title": operation["title"], "payload": {"id": f"text-{_short_id()}", "title": operation["title"], "content": operation["content"], "blockKind": operation["block_kind"]}}

    all_refs = {**existing_refs, **produced}
    default_order = [*existing_refs.keys(), *produced.keys()]
    requested_order = [str(ref).strip() for ref in (ordered_refs or default_order) if str(ref).strip()]
    if len(requested_order) != len(all_refs) or set(requested_order) != set(all_refs):
        return {"ok": False, "error": "ordered_refs 必须恰好包含每个保留的既有对象 item:<id> 与每个新增对象 ref 各一次。", "available_refs": list(all_refs), "skipped": skipped}
    next_items = [all_refs[ref] for ref in requested_order]
    if dry_run:
        preview = _compose_draft_preview(draft, next_items, action="apply_composition_plan")
        preview.update({"available_refs": {ref: item["id"] for ref, item in all_refs.items()}, "skipped": skipped})
        return preview
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "apply_composition_plan", "draft": saved, "skipped": skipped}


def _find_composition_candidates(query: str, limit: int = 500) -> list[dict[str, Any]]:
    keyword = str(query or "").strip()
    if not keyword:
        return []
    terms = list(dict.fromkeys([keyword, *[term for term in _candidate_query_tokens(keyword) if len(term.strip()) >= 2], re.sub(r"(定理|规律|专题|知识点)$", "", keyword).strip()]))
    terms = [term for term in terms if term]
    searchable_columns = [
        "q.question_id", "q.canonical_title", "q.module", "q.source", "qti.title_text", "qti.stem_text", "qti.source_text",
        "kp.topic1_name", "kp.topic2_name", "kp.topic3_name", "kp.source_chapter",
    ]
    where = " OR ".join(
        f"{column} LIKE '%' || ? || '%'" for term in terms for column in searchable_columns
    )
    params = [term for term in terms for _ in searchable_columns]
    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT q.question_id, q.canonical_title, q.question_type, q.difficulty, q.module, q.source,
                   qti.title_text, qti.stem_text, qti.source_text
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN question_knowledge_points qkp ON qkp.question_id = q.question_id
            LEFT JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id
            WHERE (q.status IS NULL OR q.status NOT IN ('deleted', 'archived'))
              AND ({where})
            ORDER BY q.updated_at DESC, q.question_id
            LIMIT ?
            """,
            [*params, min(max(int(limit), 1), 500)],
        ).fetchall()
    return [dict(row) for row in rows]


def _select_balanced_composition_candidates(candidates: list[dict[str, Any]], target_count: int, query: str) -> list[dict[str, Any]]:
    remaining = list(candidates)
    selected: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    seen_types: set[str] = set()
    seen_difficulties: set[str] = set()
    keyword = str(query).casefold()
    while remaining and len(selected) < target_count:
        def score(row: dict[str, Any]) -> tuple[int, str]:
            source = str(row.get("source_text") or row.get("source") or "未标注")
            question_type = str(row.get("question_type") or "未标注")
            difficulty = str(row.get("difficulty") if row.get("difficulty") is not None else "未标注")
            title = str(row.get("title_text") or row.get("canonical_title") or "").casefold()
            return (
                (4 if source not in seen_sources else 0)
                + (3 if question_type not in seen_types else 0)
                + (2 if difficulty not in seen_difficulties else 0)
                + (2 if keyword and keyword in title else 0),
                str(row["question_id"]),
            )
        choice = max(remaining, key=score)
        remaining.remove(choice)
        selected.append(choice)
        seen_sources.add(str(choice.get("source_text") or choice.get("source") or "未标注"))
        seen_types.add(str(choice.get("question_type") or "未标注"))
        seen_difficulties.add(str(choice.get("difficulty") if choice.get("difficulty") is not None else "未标注"))
    return selected


@server.tool()
def curate_questions_to_composition_workbench(
    query: str,
    target_count: int = 20,
    draft_id: str | None = None,
    insert_at: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """一键从正式题库检索某主题全部候选题，并按题型、难度、来源均衡精选后加入组卷工作台。适合“找所有动能定理题，精选20道加入当前工作台”。只写组卷草稿，不修改正式题库。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    keyword = str(query or "").strip()
    count = min(max(int(target_count or 20), 1), 100)
    if not keyword:
        return {"ok": False, "error": "检索主题 query 不能为空，例如：动能定理。"}
    candidates = _find_composition_candidates(keyword)
    existing_ids = {str(item.get("question_id") or "") for item in draft.get("items") or [] if item.get("type") == "question"}
    available = [row for row in candidates if str(row["question_id"]) not in existing_ids]
    chosen_rows = _select_balanced_composition_candidates(available, count, keyword)
    chosen_ids = [str(row["question_id"]) for row in chosen_rows]
    summaries = _fetch_formal_question_summaries(chosen_ids)
    new_items = [
        {"id": f"compose-question-{_short_id()}", "type": "question", "position": 0, "question_id": question_id,
         "title": summaries[question_id]["title"] or question_id, "score": None, "payload": summaries[question_id]}
        for question_id in chosen_ids if question_id in summaries
    ]
    items = list(draft.get("items") or [])
    position = _compose_insert_position(items, insert_at)
    next_items = [*items[:position], *new_items, *items[position:]]
    diversity = {
        "question_types": sorted({str(row.get("question_type") or "未标注") for row in chosen_rows}),
        "difficulties": sorted({str(row.get("difficulty") if row.get("difficulty") is not None else "未标注") for row in chosen_rows}),
        "sources": sorted({str(row.get("source_text") or row.get("source") or "未标注") for row in chosen_rows}),
    }
    if dry_run:
        preview = _compose_draft_preview(draft, next_items, action="curate_questions_to_workbench")
        preview.update({
            "query": keyword,
            "candidate_count": len(candidates),
            "excluded_already_in_workbench": len(candidates) - len(available),
            "selected_count": len(new_items),
            "selected_question_ids": chosen_ids,
            "selection_policy": "优先覆盖不同来源、题型和难度；题干标题直接匹配主题时优先。",
            "diversity": diversity,
        })
        return preview
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "curate_questions_to_workbench", "draft": saved, "query": keyword, "candidate_count": len(candidates), "selected_question_ids": chosen_ids, "diversity": diversity}


@server.tool()
def list_knowledge_tree(keyword: str | None = None, limit: int = 200) -> dict[str, Any]:
    """读取正式知识点树；关键词命中时返回命中节点所在的完整二级分支。只读。"""
    clean_keyword = str(keyword or "").strip()
    bounded_limit = min(max(int(limit or 200), 1), 500)
    rows = _query_knowledge_points(keyword="", limit=500)
    if clean_keyword:
        matches = _metadata_management_service().search_knowledge_points(
            clean_keyword, limit=100
        )
        matched_topic2_ids = {str(item["topic2_id"]) for item in matches}
        rows = [row for row in rows if str(row["topic2_id"]) in matched_topic2_ids]
    rows = rows[:bounded_limit]
    tree: dict[str, Any] = {}
    for row in rows:
        t1 = tree.setdefault(row["topic1_id"], {"id": row["topic1_id"], "name": row["topic1_name"], "children": {}})
        t2 = t1["children"].setdefault(row["topic2_id"], {"id": row["topic2_id"], "name": row["topic2_name"], "children": []})
        t2["children"].append(
            {
                "id": row["topic3_id"],
                "name": row["topic3_name"],
                "source_chapter": row["source_chapter"],
                "status": row["status"],
            }
        )
    return {
        "items": [{**topic1, "children": list(topic1["children"].values())} for topic1 in tree.values()],
        "total_topic3": len(rows),
    }


@server.tool()
def search_knowledge_points(keyword: str, limit: int = 20) -> dict[str, Any]:
    """按中文关键词模糊搜索正式知识点，返回相关度与匹配说明。只读。"""
    clean_keyword = str(keyword or "").strip()
    if not clean_keyword:
        return _tool_error("INVALID_ARGUMENT", "keyword 不能为空。", field="keyword")
    bounded_limit = min(max(int(limit or 20), 1), 100)
    try:
        items = _metadata_management_service().search_knowledge_points(
            clean_keyword, limit=bounded_limit
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)
    return {"items": items, "limit": bounded_limit, "total": len(items)}


@server.tool()
def get_question_knowledge_points(question_id: str) -> dict[str, Any]:
    """读取某道题绑定的知识点。只读。"""
    clean_question_id = str(question_id or "").strip()
    if not clean_question_id:
        return _tool_error("INVALID_ARGUMENT", "question_id 不能为空。", field="question_id")
    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM question_knowledge_points_view
            WHERE question_id = ?
            ORDER BY rank, topic3_id
            """,
            (clean_question_id,),
        ).fetchall()
    return {"question_id": clean_question_id, "items": [dict(row) for row in rows]}


@server.tool()
def create_knowledge_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    """直接新增正式知识树节点。知识目录是智能体可自治维护的元数据，不需要审核。"""
    try:
        return _metadata_management_service().create_knowledge_points(points)
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)


@server.tool()
def organize_knowledge_tree(
    assignments: list[dict[str, Any]],
    task_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """AI 一次完成知识点匹配结果落库、缺失节点创建和题目绑定。

    assignments 每项包含 question_id 与 knowledge_points（最多 3 个三级节点，
    每个节点提供 topic1/topic2/topic3 名称及可选 ID）。正式题目直接绑定；传入
    task_id 时，尚未入库的题目会同步写回当前校对草稿。元数据整理无需人工审核。
    """
    try:
        result = _metadata_management_service().organize_knowledge_tree(
            assignments, reason=reason
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)

    draft_updates = result.get("draft_updates") or []
    clean_task_id = str(task_id or "").strip()
    if draft_updates and not clean_task_id:
        result["ok"] = False
        result["error"] = "包含尚未入库的题目，请提供 task_id 以写回当前校对草稿。"
        return result
    if draft_updates:
        applied = update_review_task_draft(
            clean_task_id,
            draft_updates,
            dry_run=False,
            reason=reason or "AI 自动整理知识树",
        )
        result["review_task_update"] = applied
        result["ok"] = bool(result.get("ok")) and bool(applied.get("ok"))
    return result


@server.tool()
def batch_update_question_metadata(
    updates: list[dict[str, Any]],
    reason: str | None = None,
) -> dict[str, Any]:
    """直接统一标签、知识点、难度、题型和规范化来源；不能修改题目正文或发布状态。"""
    try:
        return _metadata_management_service().batch_update_question_metadata(updates, reason=reason)
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)


@server.tool()
def database_boundary_report() -> dict[str, Any]:
    """说明 MCP 当前正式库/审核库边界、各库职责、遗留污染和推荐工具路由。只读。"""
    formal_path = _formal_db_path()
    review_path = _review_db_path()
    same_file = False
    try:
        same_file = formal_path.exists() and review_path.exists() and formal_path.resolve() == review_path.resolve()
    except OSError:
        same_file = False

    with _connect_formal_read_db() as formal_conn:
        formal_counts = {
            table: _safe_count(formal_conn, table)
            for table in [
                "questions",
                "question_text_index",
                "knowledge_points",
                "question_knowledge_points",
                "question_sources",
                "question_versions",
                "question_search_fts",
            ]
        }
        legacy_review_queue_count = _safe_count(formal_conn, "review_queue")
        legacy_import_tasks_count = _safe_count(formal_conn, "import_pipeline_tasks")

    with _connect_review_db() as review_conn:
        review_counts = {
            "import_pipeline_tasks": _safe_count(review_conn, "import_pipeline_tasks"),
            "review_queue": _safe_count(review_conn, "review_queue"),
            "review_workspace_ignored_sessions": _safe_count(review_conn, "review_workspace_ignored_sessions"),
        }
        review_task_statuses = [
            dict(row)
            for row in review_conn.execute(
                """
                SELECT task_type, status, COUNT(*) AS count
                FROM import_pipeline_tasks
                GROUP BY task_type, status
                ORDER BY count DESC, task_type, status
                """
            ).fetchall()
        ]
        review_queue_statuses = [
            dict(row)
            for row in review_conn.execute(
                """
                SELECT queue_type, status, COUNT(*) AS count
                FROM review_queue
                GROUP BY queue_type, status
                ORDER BY count DESC, queue_type, status
                """
            ).fetchall()
        ]
        pending_review_tasks = []
        for row in review_conn.execute(
            """
            SELECT task_id, task_type, status, updated_at, input_summary_json, result_json
            FROM import_pipeline_tasks
            WHERE task_type IN ('ai_generated_review', 'ai_generated_knowledge_review', 'import_confirmed')
            ORDER BY updated_at DESC
            LIMIT 20
            """
        ).fetchall():
            summary = _parse_json_dict(row["input_summary_json"])
            result = _parse_json_dict(row["result_json"])
            pending_review_tasks.append(
                {
                    "task_id": row["task_id"],
                    "task_type": row["task_type"],
                    "status": row["status"],
                    "question_count": int(result.get("question_count") or summary.get("question_count") or 0),
                    "knowledge_count": int(result.get("knowledge_count") or summary.get("knowledge_count") or 0),
                    "updated_at": row["updated_at"],
                }
            )

    issues = []
    if same_file:
        issues.append({"code": "formal_and_review_db_same_file", "severity": "high", "message": "正式库和审核库指向同一个文件，会破坏读写边界。"})
    if legacy_review_queue_count:
        issues.append({"code": "legacy_review_queue_in_formal_db", "severity": "medium", "count": legacy_review_queue_count, "message": "正式库仍存在历史 review_queue；当前 MCP 不应把它当作有效校对队列。"})
    if legacy_import_tasks_count:
        issues.append({"code": "legacy_import_tasks_in_formal_db", "severity": "low", "count": legacy_import_tasks_count, "message": "正式库仍有历史导入任务；当前有效审核任务来自审核库。"})

    return {
        "ok": True,
        "database_boundary": {
            "canonical_database": {
                "path": str(formal_path),
                "role": "标准/正式题库。题目正文只读；标签、知识点、难度、题型和规范化来源可由智能体直接维护。",
                "counts": formal_counts,
            },
            "review_database": {
                "path": str(review_path),
                "role": "审核/校对工作区。送审题、导入草稿、AI 生成草稿、review_queue 均在这里读写。",
                "counts": review_counts,
                "task_statuses": review_task_statuses,
                "queue_statuses": review_queue_statuses,
                "recent_review_tasks": pending_review_tasks,
            },
            "same_file": same_file,
        },
        "routing": {
            "review_center_first": ["list_review_tasks", "get_review_task", "get_review_task_full", "clean_review_task_latex", "update_review_task_draft"],
            "canonical_read_only": ["search_questions", "get_questions_by_ids", "list_knowledge_tree", "search_knowledge_points", "get_question_knowledge_points", "find_similar_questions"],
            "canonical_metadata_write": ["create_knowledge_points", "batch_update_question_metadata"],
            "canonical_controlled_content_workflow": ["return_question_to_review", "rollback_change_batch"],
            "rule": "用户说送审、校对中心、草稿、审核任务、那 15 道题时，先走审核库工具；用户明确说正式题库/已入库/组卷找题时，才走正式库检索。",
        },
        "issues": issues,
        "next_tool_when_user_says_submitted_or_review": "list_review_tasks",
    }


@server.tool()
def database_health_report() -> dict[str, Any]:
    """盘点正式数据库健康度，并附带审核库边界摘要。只读；不要用正式库 review_queue 判断校对中心。"""
    db_path = _formal_db_path()
    with _connect_formal_read_db() as conn:
        counts = {}
        for table in [
            "questions",
            "question_text_index",
            "knowledge_points",
            "question_knowledge_points",
            "question_sources",
            "question_versions",
            "question_search_fts",
        ]:
            counts[table] = _safe_count(conn, table)

        status_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT status, review_status, COUNT(*) AS count
                FROM questions
                GROUP BY status, review_status
                ORDER BY count DESC, status, review_status
                """
            ).fetchall()
        ]
        missing_text_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            WHERE qti.question_id IS NULL
            """
        ).fetchone()[0]
        orphan_text_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM question_text_index qti
            LEFT JOIN questions q ON q.question_id = qti.question_id
            WHERE q.question_id IS NULL
            """
        ).fetchone()[0]
        missing_kp_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM question_knowledge_points qkp
            LEFT JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id
            WHERE kp.topic3_id IS NULL
            """
        ).fetchone()[0]
        unbound_question_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM questions q
            LEFT JOIN question_knowledge_points qkp ON qkp.question_id = q.question_id
            WHERE qkp.question_id IS NULL
            """
        ).fetchone()[0]
        legacy_review_queue_count = _safe_count(conn, "review_queue") or 0

        duplicate_tag_questions = []
        for row in conn.execute(
            """
            SELECT q.question_id, q.canonical_title, qti.tags_json
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            ORDER BY q.question_id
            """
        ).fetchall():
            tags = _parse_tags(row["tags_json"])
            raw_tags = _raw_tags(row["tags_json"])
            if len(raw_tags) != len(tags):
                duplicate_tag_questions.append(
                    {
                        "question_id": row["question_id"],
                        "title": row["canonical_title"],
                        "raw_tags": raw_tags,
                        "normalized_tags": tags,
                    }
                )

    with _connect_review_db() as review_conn:
        review_counts = {
            "import_pipeline_tasks": _safe_count(review_conn, "import_pipeline_tasks"),
            "review_queue": _safe_count(review_conn, "review_queue"),
        }
        review_queue_rows = [
            dict(row)
            for row in review_conn.execute(
                """
                SELECT queue_type, status, COUNT(*) AS count
                FROM review_queue
                GROUP BY queue_type, status
                ORDER BY count DESC, queue_type, status
                """
            ).fetchall()
        ]
        review_task_rows = [
            dict(row)
            for row in review_conn.execute(
                """
                SELECT task_type, status, COUNT(*) AS count
                FROM import_pipeline_tasks
                GROUP BY task_type, status
                ORDER BY count DESC, task_type, status
                """
            ).fetchall()
        ]

    issues = []
    if missing_text_count:
        issues.append({"code": "missing_text_index", "severity": "high", "count": missing_text_count})
    if orphan_text_count:
        issues.append({"code": "orphan_text_index", "severity": "high", "count": orphan_text_count})
    if missing_kp_count:
        issues.append({"code": "knowledge_link_missing_topic", "severity": "high", "count": missing_kp_count})
    if unbound_question_count:
        issues.append({"code": "questions_without_knowledge_directory", "severity": "medium", "count": unbound_question_count})
    if legacy_review_queue_count:
        issues.append({"code": "legacy_review_queue_in_formal_db", "severity": "medium", "count": legacy_review_queue_count})
    if duplicate_tag_questions:
        issues.append({"code": "duplicate_or_messy_tags", "severity": "low", "count": len(duplicate_tag_questions)})

    recommendations = [
        "以 knowledge_points + question_knowledge_points 作为知识目录唯一正式来源，questions.module 只作为兼容展示字段。",
        "校对中心以审核库 review_workspace.sqlite3 为准，不要读取正式库中的历史 review_queue。",
        "标签只保留横向检索维度，避免把知识目录重复塞进标签。",
    ]
    return {
        "database_path": str(db_path),
        "canonical_database_path": str(db_path),
        "review_database_path": str(_review_db_path()),
        "counts": counts,
        "question_statuses": status_rows,
        "review_workspace": {
            "counts": review_counts,
            "review_queue": review_queue_rows,
            "review_tasks": review_task_rows,
        },
        "legacy_formal_review_queue_count": legacy_review_queue_count,
        "issues": issues,
        "duplicate_tag_samples": duplicate_tag_questions[:20],
        "recommendations": recommendations,
        "routing_hint": "送审/校对中心/草稿任务请使用 list_review_tasks 或 list_review_queue；正式题库健康才看本报告的 counts/question_statuses。",
    }


@server.tool()
def list_review_queue(
    status: str | None = "pending",
    queue_type: str | None = None,
    include_orphans: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """列出审核库校对队列 review_queue，并只读补充正式题库摘要。"""
    limit = min(max(int(limit or 50), 1), 100)
    params: list[Any] = []
    where_parts: list[str] = []
    if status and str(status).strip().lower() not in {"all", "全部", "*"}:
        where_parts.append("rq.status = ?")
        params.append(str(status).strip())
    if queue_type and str(queue_type).strip().lower() not in {"all", "全部", "*"}:
        where_parts.append("rq.queue_type = ?")
        params.append(str(queue_type).strip())
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    params.append(limit)

    with _connect_review_db() as conn:
        if not _table_exists(conn, "review_queue"):
            return {"items": [], "total": 0, "table_missing": True, "message": "review_queue 表不存在。"}
        rows = conn.execute(
            f"""
            SELECT
                rq.review_id, rq.entity_type, rq.entity_id, rq.queue_type, rq.status,
                rq.priority, rq.reason, rq.payload_json, rq.created_at, rq.updated_at
            FROM review_queue rq
            {where_sql}
            ORDER BY rq.priority DESC, rq.created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    question_ids = [
        str(row["entity_id"])
        for row in rows
        if row["entity_type"] == "question" and str(row["entity_id"] or "").strip()
    ]
    question_map = _fetch_formal_question_summaries(question_ids)
    orphan_count = sum(
        1
        for row in rows
        if row["entity_type"] == "question" and str(row["entity_id"]) not in question_map
    )
    if not include_orphans:
        rows = [
            row
            for row in rows
            if row["entity_type"] != "question" or str(row["entity_id"]) in question_map
        ]

    items = []
    for row in rows:
        payload = _parse_json_dict(row["payload_json"])
        question = question_map.get(str(row["entity_id"]), {})
        items.append(
            {
                "review_id": row["review_id"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "queue_type": row["queue_type"],
                "status": row["status"],
                "priority": row["priority"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "question": {
                    "question_id": row["entity_id"] if row["entity_type"] == "question" else None,
                    "title": question.get("title") or payload.get("title"),
                    "question_type": question.get("question_type"),
                    "difficulty": question.get("difficulty"),
                    "status": question.get("status"),
                    "review_status": question.get("review_status"),
                    "stem_preview": _preview_text(question.get("stem_text")),
                    "tags": question.get("tags", []),
                    "source": question.get("source"),
                },
                "payload": payload,
            }
        )
    return {
        "items": items,
        "total": len(items),
        "limit": limit,
        "orphan_count": orphan_count,
        "review_database_path": str(_review_db_path()),
    }


@server.tool()
def import_word_folder_to_review(
    folder_path: str,
    recursive: bool = False,
    dry_run: bool = True,
    use_ai_cleanup: bool = True,
    max_files: int = 20,
    max_file_size_mb: int = 30,
    file_filter: str | None = None,
    skip_if_duplicate: bool = True,
) -> dict[str, Any]:
    """批量导入指定文件夹中的 Word 文件到审核库。

    依次执行：读取 .doc/.docx -> 创建导入批次 -> 转 Markdown -> 清洗 -> 结构化题目 ->
    生成审核任务。默认 dry_run=true 只列出计划；确认目录和数量后再 dry_run=false。
    不会向正式题库写入任何题目。
    """
    raw_folder = str(folder_path or "").strip()
    if not raw_folder:
        return {"ok": False, "error": "folder_path 不能为空。"}

    folder = Path(raw_folder).expanduser()
    try:
        folder = folder.resolve(strict=True)
    except FileNotFoundError:
        return {"ok": False, "error": f"文件夹不存在：{raw_folder}"}
    if not folder.is_dir():
        return {"ok": False, "error": f"路径不是文件夹：{folder}"}

    pattern = str(file_filter or "").strip()
    if any(separator in pattern for separator in ("/", "\\")) or len(pattern) > 120:
        return _tool_error(
            "INVALID_ARGUMENT",
            "file_filter 只能是文件名通配符，不能包含目录分隔符，长度不能超过 120。",
            field="file_filter",
        )

    file_limit = min(max(int(max_files or 20), 1), 50)
    size_limit_bytes = min(max(int(max_file_size_mb or 30), 1), 100) * 1024 * 1024
    iterator = folder.rglob("*") if recursive else folder.glob("*")
    candidates = sorted(
        (
            item
            for item in iterator
            if item.is_file()
            and item.suffix.lower() in {".doc", ".docx"}
            and (not pattern or fnmatch.fnmatchcase(item.name.casefold(), pattern.casefold()))
        ),
        key=lambda item: (str(item.relative_to(folder)).casefold(), str(item)),
    )

    eligible: list[Path] = []
    skipped: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    file_digests: dict[Path, str] = {}
    service = _import_service()
    for item in candidates:
        size = item.stat().st_size
        relative = str(item.relative_to(folder))
        if size > size_limit_bytes:
            skipped.append({"file": relative, "reason": f"文件超过 {max_file_size_mb} MB 限制", "size_bytes": size})
            continue
        if len(eligible) >= file_limit:
            skipped.append({"file": relative, "reason": f"超过单次 {file_limit} 个文件限制", "size_bytes": size})
            continue
        digest = hashlib.sha256(item.read_bytes()).hexdigest()
        file_digests[item] = digest
        matches = service.find_import_batches_by_sha256(digest)
        if matches:
            duplicate = {
                "file": relative,
                "size_bytes": size,
                "source_sha256": digest,
                "existing_batches": matches,
                "action": "skipped" if skip_if_duplicate else "reimport",
            }
            duplicates.append(duplicate)
            if skip_if_duplicate:
                continue
        eligible.append(item)

    plan = [
        {
            "file": str(item.relative_to(folder)),
            "size_bytes": item.stat().st_size,
            "source_sha256": file_digests.get(item),
        }
        for item in eligible
    ]
    base = {
        "ok": True,
        "database_scope": "review_workspace",
        "canonical_database_written": False,
        "folder_path": str(folder),
        "recursive": bool(recursive),
        "file_filter": pattern or None,
        "skip_if_duplicate": bool(skip_if_duplicate),
        "dry_run": bool(dry_run),
        "file_count": len(eligible),
        "files": plan,
        "duplicates": duplicates,
        "skipped": skipped,
        "next_step": "确认文件清单后，以相同参数调用 dry_run=false 执行导入。",
    }
    if dry_run:
        return base
    if not eligible:
        return {**base, "ok": False, "error": "未找到可导入的 .doc 或 .docx 文件。"}

    imported: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in eligible:
        relative = str(item.relative_to(folder))
        try:
            batch = service.create_batch_from_upload(item.name, item.read_bytes())
            batch_id = str(batch["batch_id"])
            pandoc_task = service.run_batch_pandoc(batch_id)
            if pandoc_task.status == "failed":
                raise RuntimeError(pandoc_task.error or "Word 转换失败")

            clean_task = service.run_batch_ai_clean(batch_id, use_ai=bool(use_ai_cleanup))
            if clean_task.status == "failed":
                raise RuntimeError(clean_task.error or "题目清洗失败")

            structure_task = service.structure_batch_questions(batch_id, use_ai_refine=bool(use_ai_cleanup))
            if structure_task.status == "failed":
                raise RuntimeError(structure_task.error or "题目结构化失败")
            structured = structure_task.result or {}
            questions = structured.get("questions") if isinstance(structured.get("questions"), list) else []
            review_task = service.confirm_batch_questions(batch_id, questions)
            imported.append(
                {
                    "file": relative,
                    "batch_id": batch_id,
                    "review_task_id": review_task.task_id,
                    "review_url": f"/review/{review_task.task_id}",
                    "question_count": len(questions),
                    "cleanup": "ai_or_local_fallback" if use_ai_cleanup else "local_only",
                    "warnings": list((clean_task.result or {}).get("warnings") or []),
                }
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"file": relative, "error": str(exc)})

    return {
        **base,
        "dry_run": False,
        "imported": imported,
        "failed": failed,
        "duplicate_count": len(duplicates),
        "imported_count": len(imported),
        "failed_count": len(failed),
        "next_step": "使用 list_review_tasks 查看已创建的审核任务；需要专项公式规范化时再调用 clean_review_task_latex。",
    }


@server.tool()
def list_review_tasks(
    status: str | None = None,
    task_type: str | None = None,
    question_count: int | None = None,
    knowledge_count: int | None = None,
    keyword: str | None = None,
    reviewable_only: bool = True,
    limit: int = 80,
) -> dict[str, Any]:
    """列出审核库中的校对任务。只读。送审/校对/那15道题/公式清洗必须先用本工具定位任务，不要先查正式题库。"""
    limit = min(max(int(limit or 80), 1), 200)
    params: list[Any] = []
    where_parts: list[str] = []
    if status and str(status).strip().lower() not in {"all", "全部", "*"}:
        where_parts.append("status = ?")
        params.append(str(status).strip())
    if task_type and str(task_type).strip().lower() not in {"all", "全部", "*"}:
        where_parts.append("task_type = ?")
        params.append(str(task_type).strip())
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    raw_limit = min(max(limit * 4, limit), 500)
    params.append(raw_limit)

    with _connect_review_db() as conn:
        if not _table_exists(conn, "import_pipeline_tasks"):
            return {"items": [], "total": 0, "table_missing": True, "message": "import_pipeline_tasks 表不存在。"}
        rows = conn.execute(
            f"""
            SELECT task_id, task_type, status, created_at, updated_at,
                   input_summary_json, result_json, error
            FROM import_pipeline_tasks
            {where_sql}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    items = []
    review_task_types = {
        "ai_generated_review",
        "ai_generated_knowledge_review",
        "import_confirmed",
        "structure_questions",
        "ai_parse_document",
        "parse_structured_questions",
    }
    for row in rows:
        if reviewable_only and not task_type and row["task_type"] not in review_task_types:
            continue
        summary = _parse_json_dict(row["input_summary_json"])
        result = _parse_json_dict(row["result_json"])
        questions = result.get("questions") if isinstance(result.get("questions"), list) else []
        knowledge_drafts = result.get("knowledge_drafts") if isinstance(result.get("knowledge_drafts"), list) else []
        is_reviewable = (
            row["task_type"] in {"ai_generated_review", "ai_generated_knowledge_review", "import_confirmed"}
            or bool(questions)
            or bool(knowledge_drafts)
        )
        if reviewable_only and not is_reviewable:
            continue
        warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        item = (
            {
                "task_id": row["task_id"],
                "task_type": row["task_type"],
                "status": row["status"],
                "batch_id": str(result.get("batch_id") or summary.get("batch_id") or ""),
                "title": str(
                    result.get("title")
                    or result.get("source")
                    or summary.get("source")
                    or ("AI 生成审核" if row["task_type"] == "ai_generated_review" else "导入校对任务")
                ),
                "question_count": int(result.get("question_count") or summary.get("question_count") or 0),
                "knowledge_count": int(result.get("knowledge_count") or summary.get("knowledge_count") or 0),
                "source": str(result.get("source") or summary.get("source") or ""),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "warnings": [str(item) for item in warnings],
                "error": row["error"],
                "reviewable": is_reviewable,
            }
        )
        if question_count is not None and int(item["question_count"]) != int(question_count):
            continue
        if knowledge_count is not None and int(item["knowledge_count"]) != int(knowledge_count):
            continue
        if keyword and str(keyword).strip():
            haystack = " ".join(
                str(item.get(key) or "")
                for key in ("task_id", "task_type", "batch_id", "title", "source")
            )
            if str(keyword).strip().casefold() not in haystack.casefold():
                continue
        items.append(item)
        if len(items) >= limit:
            break
    return {"items": items, "total": len(items), "limit": limit, "review_database_path": str(_review_db_path())}


@server.tool()
def get_review_task(task_id: str, content_limit: int = 20) -> dict[str, Any]:
    """读取审核库中一个校对任务的草稿内容摘要。只读。"""
    tid = str(task_id or "").strip()
    if not tid:
        return _tool_error("INVALID_ARGUMENT", "task_id 不能为空。", field="task_id")
    with _connect_review_db() as conn:
        if not _table_exists(conn, "import_pipeline_tasks"):
            return {"ok": False, "table_missing": True, "error": "import_pipeline_tasks 表不存在。"}
        row = conn.execute(
            """
            SELECT task_id, task_type, status, created_at, updated_at,
                   input_summary_json, result_json, error
            FROM import_pipeline_tasks
            WHERE task_id = ?
            """,
            (tid,),
        ).fetchone()
    if row is None:
        return {"ok": False, "status": "missing", "task_id": tid, "error": "校对任务不存在。"}

    limit = min(max(int(content_limit or 20), 1), 80)
    summary = _parse_json_dict(row["input_summary_json"])
    result = _parse_json_dict(row["result_json"])
    questions = result.get("questions") if isinstance(result.get("questions"), list) else []
    knowledge_drafts = result.get("knowledge_drafts") if isinstance(result.get("knowledge_drafts"), list) else []
    return {
        "ok": True,
        "task": {
            "task_id": row["task_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "input_summary": summary,
            "batch_id": str(result.get("batch_id") or summary.get("batch_id") or ""),
            "source": str(result.get("source") or summary.get("source") or ""),
            "question_count": int(result.get("question_count") or summary.get("question_count") or len(questions)),
            "knowledge_count": int(result.get("knowledge_count") or summary.get("knowledge_count") or len(knowledge_drafts)),
            "warnings": [str(item) for item in result.get("warnings") or []],
            "error": row["error"],
        },
        "questions": [_review_question_summary(item, index) for index, item in enumerate(questions[:limit], start=1)],
        "knowledge_drafts": [
            _review_knowledge_summary(item, index)
            for index, item in enumerate(knowledge_drafts[:limit], start=1)
        ],
        "content_limit": limit,
    }


@server.tool()
def get_review_task_full(
    task_id: str,
    question_ids: list[str] | None = None,
    include_knowledge: bool = True,
) -> dict[str, Any]:
    """读取审核库中校对任务的完整草稿字段，不截断题干。只读。"""
    tid = str(task_id or "").strip()
    if not tid:
        return _tool_error("INVALID_ARGUMENT", "task_id 不能为空。", field="task_id")
    with _connect_review_db() as conn:
        if not _table_exists(conn, "import_pipeline_tasks"):
            return {"ok": False, "table_missing": True, "error": "import_pipeline_tasks 表不存在。"}
        row = conn.execute(
            """
            SELECT task_id, task_type, status, created_at, updated_at,
                   input_summary_json, result_json, error
            FROM import_pipeline_tasks
            WHERE task_id = ?
            """,
            (tid,),
        ).fetchone()
    if row is None:
        return {"ok": False, "status": "missing", "task_id": tid, "error": "校对任务不存在。"}

    summary = _parse_json_dict(row["input_summary_json"])
    result = _parse_json_dict(row["result_json"])
    questions = result.get("questions") if isinstance(result.get("questions"), list) else []
    wanted = {str(item).strip() for item in (question_ids or []) if str(item).strip()}
    if wanted:
        questions = [
            item
            for item in questions
            if isinstance(item, dict)
            and str(item.get("question_id") or item.get("id") or item.get("draft_id") or "").strip() in wanted
        ]
    knowledge = result.get("knowledge_drafts") if isinstance(result.get("knowledge_drafts"), list) else []
    return {
        "ok": True,
        "task": {
            "task_id": row["task_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "input_summary": summary,
            "batch_id": str(result.get("batch_id") or summary.get("batch_id") or ""),
            "source": str(result.get("source") or summary.get("source") or ""),
            "question_count": int(result.get("question_count") or summary.get("question_count") or len(questions)),
            "knowledge_count": int(result.get("knowledge_count") or summary.get("knowledge_count") or len(knowledge)),
            "warnings": [str(item) for item in result.get("warnings") or []],
            "error": row["error"],
        },
        "questions": questions,
        "knowledge_drafts": knowledge if include_knowledge else [],
        "full_content": True,
    }


@server.tool()
def find_duplicate_review_tasks(
    task_type: str | None = None,
    source: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """按文件哈希或来源检测审核工作区中的重复任务。只读。"""
    try:
        return _import_service().find_duplicate_review_tasks(
            task_type=task_type,
            source=source,
            limit=limit,
        )
    except (ValueError, sqlite3.Error) as exc:
        return _tool_error("REVIEW_TASK_QUERY_ERROR", str(exc), retryable=True)


@server.tool()
def delete_review_tasks(task_ids: list[str], confirmed: bool = False) -> dict[str, Any]:
    """批量删除已结束的审核任务；confirmed=false 时只返回预览。"""
    normalized = list(dict.fromkeys(str(item).strip() for item in task_ids if str(item).strip()))
    if not normalized:
        return _tool_error("INVALID_ARGUMENT", "task_ids 至少需要一个任务号。", field="task_ids")
    if len(normalized) > 50:
        return _tool_error("LIMIT_EXCEEDED", "一次最多删除 50 个审核任务。", field="task_ids")
    previews = []
    for task_id in normalized:
        result = get_review_task(task_id, content_limit=1)
        if result.get("ok"):
            previews.append(result["task"])
        else:
            previews.append({"task_id": task_id, "status": result.get("status") or "missing", "error": result.get("error")})
    if not confirmed:
        return {
            "ok": True,
            "confirmed": False,
            "items": previews,
            "requires_confirmation": True,
            "message": "当前仅预览；确认任务清单后，以 confirmed=true 再次调用。",
        }
    result = _import_service().delete_review_tasks(normalized)
    result.update({"confirmed": True, "preview": previews})
    return result


@server.tool()
def suggest_knowledge_points_for_task(
    task_id: str,
    question_ids: list[str] | None = None,
    max_suggestions: int = 3,
) -> dict[str, Any]:
    """为审核任务中的题目推荐正式知识树节点；只推荐，不自动修改草稿。"""
    full = get_review_task_full(task_id, question_ids=question_ids, include_knowledge=False)
    if not full.get("ok"):
        return full
    questions = full.get("questions") if isinstance(full.get("questions"), list) else []
    result = _metadata_management_service().suggest_knowledge_points(
        [item for item in questions if isinstance(item, dict)],
        max_suggestions=max_suggestions,
    )
    result["task_id"] = str(task_id).strip()
    return result


@server.tool()
def clean_review_task_latex(
    task_id: str,
    question_ids: list[str] | None = None,
    dry_run: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    """清理当前校对草稿中的 Markdown 斜体公式。默认预览，确认后 dry_run=false 才写入。"""
    full = get_review_task_full(task_id)
    if not full.get("ok"):
        return full
    questions = full.get("questions") if isinstance(full.get("questions"), list) else []
    wanted = {str(item).strip() for item in (question_ids or []) if str(item).strip()}
    changed: list[dict[str, Any]] = []
    total_replacements = 0
    cleaned_questions: list[Any] = []
    for raw in questions:
        if not isinstance(raw, dict):
            cleaned_questions.append(raw)
            continue
        qid = str(raw.get("question_id") or raw.get("id") or raw.get("draft_id") or "").strip()
        if wanted and qid not in wanted:
            cleaned_questions.append(raw)
            continue
        cleaned, replacements = _clean_latex_value(raw)
        cleaned_questions.append(cleaned)
        if replacements:
            changed.append(
                {
                    "question_id": qid,
                    "replacements": replacements,
                }
            )
            total_replacements += replacements

    if not dry_run and changed:
        _update_review_task_questions(
            task_id,
            cleaned_questions,
            changed,
            kind="latex_cleanup",
            reason=reason,
        )
    return {
        "ok": True,
        "task_id": str(task_id).strip(),
        "dry_run": dry_run,
        "changed_count": len(changed),
        "replacement_count": total_replacements,
        "items": changed,
        "message": "预览完成，未写入当前草稿。" if dry_run else "已直接更新当前校对草稿。",
    }


@server.tool()
def update_review_task_draft(
    task_id: str,
    updates: list[dict[str, Any]],
    dry_run: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    """按题号直接更新当前校对草稿的字段。默认预览，不会生成新校对任务。"""
    if len(updates) > 100:
        return {"ok": False, "error": "一次最多修改 100 道草稿题。"}
    full = get_review_task_full(task_id)
    if not full.get("ok"):
        return full
    allowed_fields = {
        "title",
        "stem",
        "question_body",
        "options",
        "answer",
        "analysis",
        "tags",
        "knowledge_point",
        "knowledge_points",
        "topic3_ids",
        "topic1_id",
        "topic1_name",
        "topic2_id",
        "topic2_name",
        "topic3_id",
        "topic3_name",
        "question_type",
        "difficulty",
        "source",
        "year",
        "status",
        "review_status",
    }
    by_id = {
        str(item.get("question_id") or item.get("id") or item.get("draft_id") or "").strip(): item
        for item in full.get("questions", [])
        if isinstance(item, dict)
    }
    normalized: list[dict[str, Any]] = []
    for index, update in enumerate(updates):
        qid = str(update.get("question_id") or update.get("id") or "").strip()
        if not qid:
            return {"ok": False, "error": f"第 {index + 1} 项缺少 question_id。"}
        if qid not in by_id:
            return {"ok": False, "error": f"当前草稿中不存在题目 {qid}。"}
        patch = {key: value for key, value in update.items() if key not in {"question_id", "id"}}
        unknown = sorted(set(patch) - allowed_fields)
        if unknown:
            return {"ok": False, "error": f"{qid} 包含不允许修改的字段：{', '.join(unknown)}。"}
        if "question_type" in patch and patch["question_type"] not in {
            "single_choice", "multi_choice", "fill", "experiment", "calculation",
        }:
            return _tool_error(
                "INVALID_ARGUMENT",
                f"{qid} 的 question_type 不受支持：{patch['question_type']}。",
                field="updates.question_type",
            )
        if "difficulty" in patch and patch["difficulty"] is not None:
            try:
                difficulty = int(patch["difficulty"])
            except (TypeError, ValueError):
                return _tool_error("INVALID_ARGUMENT", f"{qid} 的 difficulty 必须是 1 到 5。", field="updates.difficulty")
            if difficulty < 1 or difficulty > 5:
                return _tool_error("INVALID_ARGUMENT", f"{qid} 的 difficulty 必须是 1 到 5。", field="updates.difficulty")
            patch["difficulty"] = difficulty
        if "year" in patch and patch["year"] is not None:
            try:
                year = int(patch["year"])
            except (TypeError, ValueError):
                return _tool_error("INVALID_ARGUMENT", f"{qid} 的 year 必须是有效年份。", field="updates.year")
            if year < 1900 or year > 2100:
                return _tool_error("INVALID_ARGUMENT", f"{qid} 的 year 必须在 1900 到 2100 之间。", field="updates.year")
            patch["year"] = year
        if "topic3_ids" in patch:
            topic3_ids = list(dict.fromkeys(str(item).strip() for item in patch.get("topic3_ids") or [] if str(item).strip()))
            if len(topic3_ids) > 3:
                return _tool_error("INVALID_ARGUMENT", f"{qid} 最多绑定 3 个知识点。", field="updates.topic3_ids")
            patch["topic3_ids"] = topic3_ids
        normalized.append({"question_id": qid, "patch": patch})

    updated_questions = [dict(item) if isinstance(item, dict) else item for item in full.get("questions", [])]
    preview_items: list[dict[str, Any]] = []
    changed_count = 0
    for item in normalized:
        qid = item["question_id"]
        current = next(row for row in updated_questions if isinstance(row, dict) and str(row.get("question_id") or row.get("id") or row.get("draft_id") or "").strip() == qid)
        before = {key: current.get(key) for key in item["patch"]}
        current.update(item["patch"])
        after = {key: current.get(key) for key in item["patch"]}
        changed = before != after
        changed_count += int(changed)
        preview_items.append({"question_id": qid, "before": before, "after": after, "status": "changed" if changed else "unchanged"})

    if not dry_run and changed_count:
        _update_review_task_questions(
            task_id,
            updated_questions,
            [item for item in preview_items if item["status"] == "changed"],
            kind="draft_update",
            reason=reason,
        )
    return {
        "ok": True,
        "task_id": str(task_id).strip(),
        "dry_run": dry_run,
        "changed_count": changed_count,
        "items": preview_items,
        "message": "预览完成，未写入当前草稿。" if dry_run else "已直接更新当前校对草稿。",
    }


@server.tool()
def list_question_tags(
    query: str | None = None,
    question_ids: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """读取正式题库标签，并统计标签频次。只读。适合先盘点混乱标签。"""
    rows = _query_question_tags(
        query=str(query or "").strip(),
        question_ids=question_ids or [],
        limit=min(max(int(limit or 200), 1), 500),
    )
    tag_counts: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for row in rows:
        tags = _parse_tags(row.get("tags_json"))
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        items.append(
            {
                "question_id": row["question_id"],
                "title": row["title_text"] or row["canonical_title"],
                "question_type": row["question_type"],
                "difficulty": row["difficulty"],
                "knowledge_point": row["module"],
                "tags": tags,
                "source": row["source_text"] or row["source"],
            }
        )
    catalog: list[dict[str, Any]] = []
    with _connect_formal_read_db() as conn:
        if _table_exists(conn, "tag_catalog"):
            catalog_rows = conn.execute(
                """
                SELECT tag_name, category, description
                FROM tag_catalog
                WHERE status = 'active'
                  AND (? = '' OR tag_name LIKE '%' || ? || '%' OR category LIKE '%' || ? || '%')
                ORDER BY category, tag_name
                LIMIT 500
                """,
                (str(query or "").strip(), str(query or "").strip(), str(query or "").strip()),
            ).fetchall()
            catalog = [
                {
                    "tag": row["tag_name"],
                    "category": row["category"],
                    "description": row["description"],
                    "count": tag_counts.get(row["tag_name"], 0),
                }
                for row in catalog_rows
            ]
    return {
        "items": items,
        "catalog": catalog,
        "tag_counts": [
            {"tag": tag, "count": count}
            for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "limit": limit,
    }


@server.tool()
def list_change_batches(
    change_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """列出正式库受控变更批次，用于审计和回滚前定位 batch_id。"""
    return _change_audit_service().list_batches(
        change_type=change_type,
        status=status,
        limit=limit,
    )


@server.tool()
def get_change_batch(batch_id: str) -> dict[str, Any]:
    """读取一个受控变更批次及逐项 diff。只读。"""
    return _change_audit_service().get_batch(batch_id)


@server.tool()
def rollback_change_batch(
    batch_id: str,
    dry_run: bool = True,
    reason: str | None = None,
    allow_conflicts: bool = False,
) -> dict[str, Any]:
    """按审计批次回滚正式库变更。默认只预览；确认后 dry_run=false 才执行。"""
    return _change_audit_service().rollback_batch(
        batch_id,
        dry_run=dry_run,
        reason=reason,
        allow_conflicts=allow_conflicts,
    )


@server.tool()
def batch_replace_question_tags(
    updates: list[dict[str, Any]],
    dry_run: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    """受控批量替换正式题库标签。默认只预览；确认后 dry_run=false 才写入标准库并记录审计。"""
    if len(updates) > 50:
        return {"ok": False, "error": "一次最多处理 50 道题，请分批执行。"}
    if not dry_run and not str(reason or "").strip():
        return {"ok": False, "error": "dry_run=false 时必须填写 reason，便于审计和回滚。"}

    normalized_updates: list[dict[str, Any]] = []
    for index, item in enumerate(updates):
        question_id = str(item.get("question_id") or "").strip()
        if not question_id:
            return {"ok": False, "error": f"第 {index + 1} 项缺少 question_id。"}
        tags = _normalize_tags(item.get("tags", []))
        if len(tags) > 8:
            return {"ok": False, "error": f"{question_id} 标签过多，请收紧到 8 个以内。"}
        normalized_updates.append({"question_id": question_id, "tags": tags})

    if not normalized_updates:
        return {"ok": True, "dry_run": dry_run, "changed_count": 0, "items": []}

    ids = [item["question_id"] for item in normalized_updates]
    placeholders = ",".join("?" for _ in ids)
    update_map = {item["question_id"]: item["tags"] for item in normalized_updates}
    with _connect_formal_write_db() as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty,
                   q.module, qti.tags_json
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            WHERE q.question_id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        existing = {row["question_id"]: row for row in rows}
        items: list[dict[str, Any]] = []
        changed = 0
        missing: list[str] = []

        for question_id in ids:
            row = existing.get(question_id)
            if row is None:
                missing.append(question_id)
                items.append({"question_id": question_id, "status": "missing"})
                continue

            before = _parse_tags(row["tags_json"])
            after = update_map[question_id]
            status = "unchanged" if before == after else "changed"
            if status == "changed":
                changed += 1
            items.append(
                {
                    "question_id": question_id,
                    "title": row["canonical_title"],
                    "question_type": row["question_type"],
                    "difficulty": row["difficulty"],
                    "knowledge_point": row["module"],
                    "before_tags": before,
                    "after_tags": after,
                    "before_value": before,
                    "after_value": after,
                    "status": status,
                }
            )

        batch_id: str | None = None
        if not dry_run:
            _ensure_change_audit_schema(conn)
            for item in items:
                if item.get("status") == "missing":
                    continue
                conn.execute(
                    """
                    INSERT INTO question_text_index (question_id, tags_json, source_text, created_at, updated_at)
                    VALUES (?, ?, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(question_id) DO UPDATE SET
                        tags_json = excluded.tags_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (item["question_id"], json.dumps(item["after_tags"], ensure_ascii=False)),
                )
            batch_id = _record_change_batch(
                conn,
                change_type="tag_normalization",
                reason=reason,
                items=items,
                field_name="question_text_index.tags_json",
                risk_level="low",
            )
            conn.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "changed_count": changed,
        "missing_ids": missing,
        "reason": reason,
        "items": items,
        "canonical_database_path": str(_formal_db_path()),
        "audit_batch_id": batch_id,
        "requires_confirmation": dry_run and changed > 0,
        "message": "预览完成，未写入数据库；确认后才可 dry_run=false。" if dry_run else "已批量替换正式题库标签，并记录审计批次。",
    }


@server.tool()
def return_question_to_review(
    question_id: str,
    reason: str = "题目需要回炉重造",
    dry_run: bool = True,
) -> dict[str, Any]:
    """受控把正式题库题目打回审核库校对中心。默认只预览；确认后 dry_run=false 才执行并审计。"""
    qid = str(question_id or "").strip()
    if not qid:
        return {"ok": False, "error": "question_id 不能为空。"}

    with _connect_formal_write_db() as conn:
        row = conn.execute(
            """
            SELECT question_id, canonical_title, status, review_status, review_comment
            FROM questions
            WHERE question_id = ?
            """,
            (qid,),
        ).fetchone()
        if row is None:
            return {"ok": False, "status": "missing", "question_id": qid, "error": "题目不存在。"}

        review_id = f"REV-{_short_id()}"
        item = {
            "question_id": qid,
            "title": row["canonical_title"],
            "before_status": row["status"],
            "before_review_status": row["review_status"],
            "after_status": "待校对",
            "after_review_status": "reviewing",
            "reason": reason,
            "review_id": review_id,
            "before_value": {"status": row["status"], "review_status": row["review_status"]},
            "after_value": {"status": "待校对", "review_status": "reviewing"},
        }
        if not dry_run:
            _ensure_change_audit_schema(conn)
            payload_json = json.dumps(
                {"source": "claude_mcp", "action": "return_to_review"},
                ensure_ascii=False,
            )
            conn.execute(
                """
                UPDATE questions
                SET status = '待校对',
                    review_status = 'reviewing',
                    review_comment = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE question_id = ?
                """,
                (reason, qid),
            )
            batch_id = _record_change_batch(
                conn,
                change_type="return_to_review",
                reason=reason,
                items=[{**item, "status": "changed"}],
                field_name="questions.status",
                risk_level="medium",
            )
            conn.commit()
            with _connect_review_db() as review_conn:
                review_conn.execute(
                    """
                    INSERT OR REPLACE INTO review_queue (
                        review_id, entity_type, entity_id, queue_type, status,
                        priority, reason, payload_json, created_at, updated_at
                    ) VALUES (?, 'question', ?, 'rework', 'pending', 5, ?, ?,
                              CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (review_id, qid, reason, payload_json),
                )
                review_conn.commit()
        else:
            batch_id = None

    return {
        "ok": True,
        "dry_run": dry_run,
        "canonical_database_path": str(_formal_db_path()),
        "review_database_path": str(_review_db_path()),
        "audit_batch_id": batch_id,
        "requires_confirmation": dry_run,
        "item": item,
        "message": "预览完成，未写入数据库；确认后才可 dry_run=false。" if dry_run else "已更新正式题库状态，并送入审核库校对队列。",
    }


@server.tool()
def batch_replace_question_knowledge_points(
    updates: list[dict[str, Any]],
    dry_run: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    """受控批量替换正式题库知识目录绑定。默认只预览；确认后 dry_run=false 才写入标准库并记录审计。"""
    if len(updates) > 50:
        return {"ok": False, "error": "一次最多处理 50 道题，请分批执行。"}
    if not dry_run and not str(reason or "").strip():
        return {"ok": False, "error": "dry_run=false 时必须填写 reason，便于审计和回滚。"}
    normalized = []
    for index, raw in enumerate(updates):
        question_id = str(raw.get("question_id") or "").strip()
        topic3_ids = raw.get("topic3_ids")
        if topic3_ids is None:
            topic3_ids = [raw.get("topic3_id")]
        topic3_ids = [str(item).strip() for item in topic3_ids if str(item or "").strip()]
        topic3_ids = list(dict.fromkeys(topic3_ids))
        if not question_id:
            return {"ok": False, "error": f"第 {index + 1} 项缺少 question_id。"}
        if not topic3_ids:
            return {"ok": False, "error": f"{question_id} 至少需要一个 topic3_id。"}
        if len(topic3_ids) > 3:
            return {"ok": False, "error": f"{question_id} 最多绑定 3 个知识目录节点。"}
        normalized.append({"question_id": question_id, "topic3_ids": topic3_ids})

    if not normalized:
        return {"ok": True, "dry_run": dry_run, "changed_count": 0, "items": []}

    question_ids = [item["question_id"] for item in normalized]
    all_topic_ids = sorted({topic_id for item in normalized for topic_id in item["topic3_ids"]})
    with _connect_formal_write_db() as conn:
        questions = _fetch_questions(conn, question_ids)
        topics = _fetch_topics(conn, all_topic_ids)
        items = []
        missing_questions = []
        missing_topics = sorted(set(all_topic_ids) - set(topics))
        changed_count = 0

        for item in normalized:
            qid = item["question_id"]
            qrow = questions.get(qid)
            if qrow is None:
                missing_questions.append(qid)
                items.append({"question_id": qid, "status": "missing_question"})
                continue

            before_rows = conn.execute(
                """
                SELECT rank, topic3_id
                FROM question_knowledge_points
                WHERE question_id = ?
                ORDER BY rank
                """,
                (qid,),
            ).fetchall()
            before = [row["topic3_id"] for row in before_rows]
            after = item["topic3_ids"]
            status = "unchanged" if before == after else "changed"
            if status == "changed":
                changed_count += 1
            items.append(
                {
                    "question_id": qid,
                    "title": qrow["canonical_title"],
                    "before_topic3_ids": before,
                    "after_topic3_ids": after,
                    "after_topics": [_topic_payload(topics[topic_id]) for topic_id in after if topic_id in topics],
                    "before_value": before,
                    "after_value": after,
                    "status": status,
                }
            )

        if missing_topics:
            return {
                "ok": False,
                "dry_run": dry_run,
                "error": "存在不存在或未启用的知识目录节点。",
                "missing_topic3_ids": missing_topics,
                "items": items,
            }

        batch_id: str | None = None
        if not dry_run:
            _ensure_change_audit_schema(conn)
            for item in items:
                if item.get("status") == "missing_question":
                    continue
                qid = item["question_id"]
                conn.execute("DELETE FROM question_knowledge_points WHERE question_id = ?", (qid,))
                for rank, topic3_id in enumerate(item["after_topic3_ids"], start=1):
                    conn.execute(
                        """
                        INSERT INTO question_knowledge_points (
                            link_id, question_id, topic3_id, rank, source, confidence, note,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'claude_mcp', 1.0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                        (f"QKP-{qid}-{rank}-{_short_id()}", qid, topic3_id, rank, reason),
                    )
                primary = item["after_topics"][0] if item["after_topics"] else {}
                conn.execute(
                    """
                    UPDATE questions
                    SET module = ?, topic2 = ?, topic3 = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE question_id = ?
                    """,
                    (
                        primary.get("topic3_name"),
                        primary.get("topic2_name"),
                        primary.get("topic3_name"),
                        qid,
                    ),
                )
            batch_id = _record_change_batch(
                conn,
                change_type="knowledge_binding_normalization",
                reason=reason,
                items=items,
                field_name="question_knowledge_points.topic3_id",
                risk_level="high",
            )
            conn.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "changed_count": changed_count,
        "missing_question_ids": missing_questions,
        "canonical_database_path": str(_formal_db_path()),
        "audit_batch_id": batch_id,
        "requires_confirmation": dry_run and changed_count > 0,
        "items": items,
        "reason": reason,
        "message": "预览完成，未写入数据库；确认后才可 dry_run=false。" if dry_run else "已批量更新正式题库知识目录绑定，并记录审计批次。",
    }


@server.tool()
def find_similar_questions(
    question_id: str,
    limit: int = 10,
    same_question_type: bool = False,
    same_knowledge_point: bool = False,
    difficulty_tolerance: int = 99,
) -> dict[str, Any]:
    """根据某道题查找相似题，可限制同题型/同知识点。只读。"""
    result = SimilarQuestionsService().find_similar(
        question_id=question_id,
        limit=min(max(int(limit or 10), 1), 30),
        same_question_type=same_question_type,
        same_knowledge_point=same_knowledge_point,
        difficulty_tolerance=int(difficulty_tolerance or 99),
    )
    return _dump_model(result)


@server.tool()
def submit_ai_generated_review(
    source_text: str,
    source: str = "Claude Code MCP",
    chat_context: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """把 AI 生成的试题文本提交到审核工作台草稿。只写草稿，不写正式题库。"""
    task = _import_service().create_ai_generated_review_task(
        source_text=source_text,
        source=source,
        chat_context=chat_context,
        session_id=session_id,
    )
    result = task.result or {}
    return {
        "task_id": task.task_id,
        "review_url": f"/review/{task.task_id}",
        "batch_id": result.get("batch_id"),
        "question_count": result.get("question_count", 0),
        "warnings": result.get("warnings", []),
    }


@server.tool()
def submit_import_job(
    batch_id: str,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
) -> dict[str, Any]:
    """为已有导入批次提交识别任务。返回简短任务摘要；重复请求由正式任务 service 幂等处理。"""
    bid = str(batch_id or "").strip()
    if not bid:
        return {"ok": False, "error": "batch_id 不能为空。"}
    try:
        task, audit_id = _task_center_service().submit_batch_job(
            "recognize",
            bid,
            context=_task_action_context(source, session_id, operator),
        )
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {
        "ok": True,
        "action": "submit_import_job",
        "job": _compact_job(task),
        "audit_id": audit_id,
        "message": "导入任务已受理；可用 get_job_status 查询进度。",
    }


@server.tool()
def submit_ai_clean_job(
    batch_id: str,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
) -> dict[str, Any]:
    """为已有导入批次提交 AI 清洗任务。返回简短任务摘要。"""
    bid = str(batch_id or "").strip()
    if not bid:
        return {"ok": False, "error": "batch_id 不能为空。"}
    try:
        task, audit_id = _task_center_service().submit_batch_job(
            "ai_clean",
            bid,
            context=_task_action_context(source, session_id, operator),
        )
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {
        "ok": True,
        "action": "submit_ai_clean_job",
        "job": _compact_job(task),
        "audit_id": audit_id,
        "message": "AI 清洗任务已受理；可用 get_job_status 查询进度。",
    }


@server.tool()
def submit_word_export_job(
    lesson_package: dict[str, Any],
    include_answers: bool = False,
    include_analysis: bool = False,
    file_name: str | None = None,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
) -> dict[str, Any]:
    """提交服务端 Word 导出任务；仅返回任务 ID、摘要和下载地址。"""
    return _submit_export_job(
        "word",
        lesson_package,
        include_answers=include_answers,
        include_analysis=include_analysis,
        file_name=file_name,
        context=_task_action_context(source, session_id, operator),
    )


@server.tool()
def submit_pptx_export_job(
    lesson_package: dict[str, Any],
    include_answers: bool = False,
    include_analysis: bool = False,
    file_name: str | None = None,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
) -> dict[str, Any]:
    """提交服务端 PPTX 导出任务；仅返回任务 ID、摘要和下载地址。"""
    return _submit_export_job(
        "pptx",
        lesson_package,
        include_answers=include_answers,
        include_analysis=include_analysis,
        file_name=file_name,
        context=_task_action_context(source, session_id, operator),
    )


@server.tool()
def get_job_status(task_id: str) -> dict[str, Any]:
    """查询单个后台任务状态。只读。"""
    tid = str(task_id or "").strip()
    if not tid:
        return _tool_error("INVALID_ARGUMENT", "task_id 不能为空。", field="task_id")
    try:
        task = _task_center_service().get_task(tid)
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {"ok": True, "job": _compact_job(task)}


@server.tool()
def list_jobs(
    statuses: list[str] | None = None,
    task_types: list[str] | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """分页查询后台任务，可按状态、类型和 ISO 时间筛选。只读。"""
    safe_page = max(1, int(page or 1))
    safe_page_size = min(max(1, int(page_size or 20)), 100)
    try:
        items, total = _task_center_service().list_tasks(
            statuses=[str(item) for item in (statuses or [])] or None,
            task_types=[str(item) for item in (task_types or [])] or None,
            created_from=_parse_job_datetime(created_from),
            created_to=_parse_job_datetime(created_to),
            page=safe_page,
            page_size=safe_page_size,
        )
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {
        "ok": True,
        "items": [_compact_job(item) for item in items],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
    }


@server.tool()
def retry_job(
    task_id: str,
    confirmed: bool = False,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
) -> dict[str, Any]:
    """重试失败或已取消任务。必须先向用户说明目标任务，再以 confirmed=true 明确确认。"""
    tid = str(task_id or "").strip()
    if not tid:
        return {"ok": False, "error": "task_id 不能为空。"}
    service = _task_center_service()
    if not confirmed:
        try:
            task = service.get_task(tid)
        except Exception as exc:  # noqa: BLE001
            return _job_tool_error(exc)
        return {
            "ok": False,
            "confirmation_required": True,
            "action": "retry_job",
            "job": _compact_job(task),
            "message": "尚未重试。请向用户确认后，以相同 task_id 和 confirmed=true 再次调用。",
        }
    try:
        task, original_task_id, audit_id = service.retry_job(
            tid,
            context=_task_action_context(source, session_id, operator, confirmed=True),
        )
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {
        "ok": True,
        "action": "retry_job",
        "original_task_id": original_task_id,
        "job": _compact_job(task),
        "audit_id": audit_id,
        "message": "已创建重试任务。",
    }


@server.tool()
def cancel_job(
    task_id: str,
    confirmed: bool = False,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
) -> dict[str, Any]:
    """请求取消尚未结束的任务。必须先向用户说明目标任务，再以 confirmed=true 明确确认。"""
    tid = str(task_id or "").strip()
    if not tid:
        return {"ok": False, "error": "task_id 不能为空。"}
    service = _task_center_service()
    if not confirmed:
        try:
            task = service.get_task(tid)
        except Exception as exc:  # noqa: BLE001
            return _job_tool_error(exc)
        return {
            "ok": False,
            "confirmation_required": True,
            "action": "cancel_job",
            "job": _compact_job(task),
            "message": "尚未取消。请向用户确认后，以相同 task_id 和 confirmed=true 再次调用。",
        }
    try:
        task, audit_id = service.cancel_job(
            tid,
            context=_task_action_context(source, session_id, operator, confirmed=True),
        )
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {
        "ok": True,
        "action": "cancel_job",
        "job": _compact_job(task),
        "audit_id": audit_id,
        "message": "已提交取消请求。",
    }


def _task_action_context(
    source: str,
    session_id: str | None,
    operator: str,
    *,
    confirmed: bool = False,
) -> TaskActionContext:
    return TaskActionContext(
        source=(str(source or "physics_vault_mcp").strip() or "physics_vault_mcp")[:120],
        session_id=(str(session_id).strip()[:160] if session_id else None),
        operator=(str(operator or "MCP user").strip() or "MCP user")[:120],
        confirmed=confirmed,
    )


def _compact_job(task: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: _mcp_scalar(task.get(key))
        for key in (
            "task_id",
            "task_type",
            "task_name",
            "status",
            "progress",
            "current_step",
            "attempt",
            "max_attempts",
            "created_at",
            "started_at",
            "finished_at",
            "error",
            "result_summary",
        )
        if task.get(key) is not None
    }
    error = compact.get("error")
    if isinstance(error, dict):
        compact["error"] = {
            "error_type": str(error.get("error_type") or "task_error")[:120],
            "user_message": str(error.get("user_message") or "任务执行失败。")[:500],
            "technical_detail": str(error.get("technical_detail") or "")[:1200] or None,
            "retryable": bool(error.get("retryable")),
        }
    if task.get("result_available"):
        compact["download_url"] = f"/api/tasks/{task.get('task_id')}/download"
    return compact


def _mcp_scalar(value: Any) -> Any:
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    return value


def _parse_job_datetime(raw: str | None):
    if not raw:
        return None
    from datetime import UTC, datetime

    parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _submit_export_job(
    export_format: Literal["word", "pptx"],
    lesson_package: dict[str, Any],
    *,
    include_answers: bool,
    include_analysis: bool,
    file_name: str | None,
    context: TaskActionContext,
) -> dict[str, Any]:
    if not isinstance(lesson_package, dict) or not str(lesson_package.get("id") or "").strip():
        return _tool_error("INVALID_ARGUMENT", "lesson_package.id 不能为空。", field="lesson_package.id")
    service = _task_center_service()
    submitter = getattr(service, "submit_export_job", None)
    if not callable(submitter):
        return {
            "ok": False,
            "capability_unavailable": True,
            "action": f"submit_{export_format}_export_job",
            "message": "服务端 Word/PPTX 导出尚未接入正式任务 service；未创建任务，也未写入数据库。",
        }
    try:
        task, audit_id = submitter(
            export_format,
            lesson_package,
            include_answers=include_answers,
            include_analysis=include_analysis,
            file_name=file_name,
            context=context,
        )
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {
        "ok": True,
        "action": f"submit_{export_format}_export_job",
        "job": _compact_job(task),
        "audit_id": audit_id,
    }


def _job_tool_error(exc: Exception) -> dict[str, Any]:
    detail = getattr(exc, "detail", None)
    message = str(detail if detail is not None else exc)
    status_code = getattr(exc, "status_code", None)
    retryable = status_code in {429, 502, 503, 504}
    return _tool_error(
        "TASK_SERVICE_ERROR",
        message[:800] or exc.__class__.__name__,
        retryable=retryable,
        status_code=status_code,
    )


def _query_knowledge_points(keyword: str, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = "WHERE status = 'active'"
    if keyword:
        where += """
        AND (
            topic3_name LIKE '%' || ? || '%'
            OR topic2_name LIKE '%' || ? || '%'
            OR topic1_name LIKE '%' || ? || '%'
            OR source_chapter LIKE '%' || ? || '%'
            OR topic3_id LIKE '%' || ? || '%'
        )
        """
        params.extend([keyword, keyword, keyword, keyword, keyword])
    params.append(limit)
    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            f"""
            SELECT topic1_id, topic1_name, topic2_id, topic2_name, topic3_id, topic3_name,
                   source_chapter, status, note
            FROM knowledge_points
            {where}
            ORDER BY topic1_id, topic2_id, topic3_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _query_question_tags(query: str, question_ids: list[str], limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_parts: list[str] = []
    if question_ids:
        safe_ids = [str(item).strip() for item in question_ids if str(item).strip()][:50]
        if safe_ids:
            where_parts.append(f"q.question_id IN ({','.join('?' for _ in safe_ids)})")
            params.extend(safe_ids)
    if query:
        where_parts.append(
            """
            (
                q.question_id LIKE '%' || ? || '%'
                OR q.canonical_title LIKE '%' || ? || '%'
                OR q.module LIKE '%' || ? || '%'
                OR qti.title_text LIKE '%' || ? || '%'
                OR qti.stem_text LIKE '%' || ? || '%'
                OR qti.tags_json LIKE '%' || ? || '%'
            )
            """
        )
        params.extend([query, query, query, query, query, query])
    params.append(limit)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty,
                   q.module, q.source, qti.title_text, qti.tags_json, qti.source_text
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            {where_sql}
            ORDER BY q.updated_at DESC, q.question_id
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_formal_question_summaries(question_ids: list[str]) -> dict[str, dict[str, Any]]:
    safe_ids = list(dict.fromkeys(str(item).strip() for item in question_ids if str(item).strip()))[:200]
    if not safe_ids:
        return {}
    placeholders = ",".join("?" for _ in safe_ids)
    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty,
                   q.status, q.review_status, q.source,
                   qti.title_text, qti.stem_text, qti.tags_json, qti.source_text
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            WHERE q.question_id IN ({placeholders})
            """,
            safe_ids,
        ).fetchall()
    return {
        row["question_id"]: {
            "question_id": row["question_id"],
            "title": row["title_text"] or row["canonical_title"],
            "question_type": row["question_type"],
            "difficulty": row["difficulty"],
            "status": row["status"],
            "review_status": row["review_status"],
            "stem_text": row["stem_text"],
            "tags": _parse_tags(row["tags_json"]),
            "source": row["source_text"] or row["source"],
        }
        for row in rows
    }


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


_REVIEW_LATEX_TEXT_KEYS = {
    "title",
    "stem",
    "question_body",
    "analysis",
    "answer",
    "raw_text",
    "content",
    "text",
}
_REVIEW_MATH_ITALIC_RE = re.compile(
    r"(?<!\*)\*([A-Za-z][A-Za-z0-9_{}\\]*(?:\s*[-+/]\s*[A-Za-z][A-Za-z0-9_{}\\]*)?)\*(?!\*)"
)


def _clean_latex_value(value: Any, key: str | None = None) -> tuple[Any, int]:
    if isinstance(value, str):
        if key is not None and key not in _REVIEW_LATEX_TEXT_KEYS:
            return value, 0
        count = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal count
            expression = " ".join(match.group(1).split())
            if not expression or len(expression) > 16:
                return match.group(0)
            count += 1
            return f"${expression}$"

        cleaned, table_count = _normalize_ocr_tables_in_text(value)
        cleaned = _REVIEW_MATH_ITALIC_RE.sub(replace, cleaned)
        cleaned, delimiter_count = normalize_math_delimiters(cleaned)
        return cleaned, count + table_count + delimiter_count
    if isinstance(value, list):
        cleaned = []
        count = 0
        for item in value:
            next_value, replacements = _clean_latex_value(item)
            cleaned.append(next_value)
            count += replacements
        return cleaned, count
    if isinstance(value, dict):
        cleaned = {}
        count = 0
        for item_key, item_value in value.items():
            next_value, replacements = _clean_latex_value(item_value, str(item_key))
            cleaned[item_key] = next_value
            count += replacements
        return cleaned, count
    return value, 0


_OCR_TABLE_BORDER_RE = re.compile(r"^\s*-{3,}(?:\s+-{3,})+\s*$")
_MATH_CELL_RE = re.compile(r"\$[^$]+\$")


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


def _update_review_task_questions(
    task_id: str,
    updated_questions: list[Any],
    changed_items: list[dict[str, Any]],
    *,
    kind: str,
    reason: str | None,
) -> None:
    with _connect_review_db() as conn:
        row = conn.execute(
            "SELECT result_json FROM import_pipeline_tasks WHERE task_id = ?",
            (str(task_id).strip(),),
        ).fetchone()
        if row is None:
            raise ValueError("校对任务不存在。")
        result = _parse_json_dict(row["result_json"])
        result["questions"] = updated_questions
        history = result.get("draft_edit_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "source": "physics_vault_mcp",
                "kind": kind,
                "reason": reason or "",
                "changed_questions": len(changed_items),
            }
        )
        result["draft_edit_history"] = history[-20:]
        conn.execute(
            """
            UPDATE import_pipeline_tasks
            SET result_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (json.dumps(result, ensure_ascii=False), str(task_id).strip()),
        )
        conn.commit()


def _safe_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
    except sqlite3.Error:
        return None


def _fetch_questions(conn: sqlite3.Connection, question_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not question_ids:
        return {}
    placeholders = ",".join("?" for _ in question_ids)
    rows = conn.execute(
        f"""
        SELECT question_id, canonical_title, question_type, difficulty, module
        FROM questions
        WHERE question_id IN ({placeholders})
        """,
        question_ids,
    ).fetchall()
    return {row["question_id"]: row for row in rows}


def _fetch_topics(conn: sqlite3.Connection, topic3_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not topic3_ids:
        return {}
    placeholders = ",".join("?" for _ in topic3_ids)
    rows = conn.execute(
        f"""
        SELECT topic1_id, topic1_name, topic2_id, topic2_name, topic3_id, topic3_name, source_chapter, status
        FROM knowledge_points
        WHERE topic3_id IN ({placeholders}) AND status = 'active'
        """,
        topic3_ids,
    ).fetchall()
    return {row["topic3_id"]: row for row in rows}


def _topic_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "topic1_id": row["topic1_id"],
        "topic1_name": row["topic1_name"],
        "topic2_id": row["topic2_id"],
        "topic2_name": row["topic2_name"],
        "topic3_id": row["topic3_id"],
        "topic3_name": row["topic3_name"],
        "source_chapter": row["source_chapter"],
    }


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _parse_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return _normalize_tags(raw)
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
        return _normalize_tags(parsed)
    except (TypeError, json.JSONDecodeError):
        return _normalize_tags(str(raw).replace("，", ",").replace("、", ",").split(","))


def _raw_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (TypeError, json.JSONDecodeError):
        pass
    return [item.strip() for item in str(raw).replace("，", ",").replace("、", ",").split(",") if item.strip()]


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _preview_text(raw: Any, limit: int = 180) -> str:
    text = " ".join(str(raw or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _review_question_summary(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"index": index, "raw_preview": _preview_text(item)}
    question_id = str(item.get("question_id") or item.get("id") or item.get("draft_id") or "").strip()
    title = str(item.get("title") or item.get("canonical_title") or item.get("stem") or "").strip()
    stem = str(item.get("stem") or item.get("stem_text") or item.get("content") or "").strip()
    tags = item.get("tags") or item.get("tag_names") or []
    knowledge = item.get("knowledge_points") or item.get("knowledge_point") or item.get("module") or ""
    risks = item.get("risks") or item.get("warnings") or item.get("validation_warnings") or []
    return {
        "index": index,
        "question_id": question_id,
        "title": _preview_text(title, 120),
        "stem_preview": _preview_text(stem or title),
        "question_type": item.get("question_type"),
        "difficulty": item.get("difficulty"),
        "answer": item.get("answer"),
        "tags": _normalize_tags(tags),
        "knowledge_points": knowledge,
        "status": item.get("status"),
        "risks": risks if isinstance(risks, list) else [str(risks)],
    }


def _review_knowledge_summary(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"index": index, "raw_preview": _preview_text(item)}
    return {
        "index": index,
        "draft_id": item.get("draft_id"),
        "topic3_id": item.get("topic3_id"),
        "topic3_name": item.get("topic3_name"),
        "topic2_id": item.get("topic2_id"),
        "topic2_name": item.get("topic2_name"),
        "topic1_id": item.get("topic1_id"),
        "topic1_name": item.get("topic1_name"),
        "keywords": item.get("keywords") or [],
        "status": item.get("status"),
        "note": _preview_text(item.get("note") or item.get("content"), 160),
    }


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace("，", ",").replace("、", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        tag = str(item).strip()
        if not tag:
            continue
        tag = " ".join(tag.split())
        if len(tag) > 30:
            tag = tag[:30].strip()
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


if __name__ == "__main__":
    server.run("stdio")
