from __future__ import annotations

import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
PACKAGES_ROOT = ROOT / "packages"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))
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

from packages.mcp_contracts.src.runtime import (  # noqa: E402
    DatabaseRuntime,
    MCPServiceFactory,
    build_mcp_system_health,
    build_task_action_context,
    build_workflow_guide,
    clean_args,
    study_sheet_template_health,
    tool_error,
)
from packages.mcp_contracts.src.operation_plan import build_operation_plan, snapshot_version  # noqa: E402
from packages.mcp_contracts.src.domains import (  # noqa: E402
    AuthoringDomain,
    ImportReviewDomain,
    ManagementDomain,
    OperationsDomain,
    SearchKnowledgeDomain,
    register_authoring_tools,
    register_import_review_tools,
    register_management_tools,
    register_operations_tools,
    register_search_knowledge_tools,
)
from packages.mcp_contracts.src.tool_registry import (  # noqa: E402
    default_tool_registry,
    profile_tool_names,
    tool_policy_manifest,
)
from physics_vault_api.paths import default_db_path, default_review_db_path, project_root  # noqa: E402
from physics_vault_api.repositories.operation_plans import OperationPlanRepository  # noqa: E402
from physics_vault_api.schemas.paper_drafts import PaperDraftItem, PaperDraftUpsertRequest  # noqa: E402
from physics_vault_api.schemas.question_search import BatchQuestionFetchRequest, QuestionSearchParams  # noqa: E402
from physics_vault_api.services.lesson_documents import (  # noqa: E402
    get_saved_handout as _get_saved_handout_store,
    list_saved_handout_versions as _list_saved_handout_versions_store,
    list_saved_handouts as _list_saved_handouts_store,
    rename_saved_handout as _rename_saved_handout_store,
    restore_saved_handout_version as _restore_saved_handout_version_store,
    update_saved_handout_format as _update_saved_handout_format_store,
)
from physics_vault_api.services.operation_plans import (  # noqa: E402
    OperationPlanError,
    OperationPlanService,
    OperationPlanVersionConflict,
)
from physics_vault_api.services.word_export_formats import (  # noqa: E402
    format_spec_for_template,
    get_word_export_template,
    list_word_export_templates as _list_word_export_templates_store,
    rename_word_export_template as _rename_word_export_template_store,
    save_word_export_template as _save_word_export_template_store,
    validate_format_spec,
)
from physics_vault_api.services.ai_assistant import _candidate_query_tokens  # noqa: E402
from physics_vault_api.services.method_feature_index import (  # noqa: E402
    METHOD_INDEX_VERSION,
    ensure_method_feature_index_current,
)
from physics_vault_api.services.method_feedback import (  # noqa: E402
    list_method_retrieval_feedback as _list_method_retrieval_feedback,
    record_method_retrieval_feedback as _record_method_retrieval_feedback,
)
from physics_vault_api.services.retrieval_learning import (  # noqa: E402
    build_method_retrieval_learning_report as _build_method_retrieval_learning_report,
)
from physics_vault_api.services.tag_maintenance import (  # noqa: E402
    diagnose_tag_maintenance as _diagnose_tag_maintenance,
    maintain_question_tags as _maintain_question_tags,
    suggest_question_tags as _suggest_question_tags,
)
from physics_vault_api.services.math_text import (  # noqa: E402
    normalize_math_delimiters,
    normalize_standard_latex,
    repair_unbalanced_inline_math,
)
from physics_vault_api.services.retrieval_method_intent import (  # noqa: E402
    detect_method_intent,
    method_query_terms,
    score_method_candidate,
)
from physics_vault_api.services.question_fingerprint import canonical_question_fingerprint  # noqa: E402
from physics_vault_api.services.paper_drafts import PaperDraftConflictError  # noqa: E402
from physics_vault_api.services.similar_questions import SimilarQuestionsService  # noqa: E402
from physics_vault_api.services.typst_exports import TypstExportError  # noqa: E402
from physics_vault_api.services.teaching_projects import (  # noqa: E402
    TeachingProjectConflictError,
    duplicate_teaching_project as _duplicate_teaching_project,
    get_teaching_project as _get_teaching_project,
    list_teaching_projects as _list_teaching_projects,
    save_teaching_project as _save_teaching_project,
)

_CLASSROOM_SESSION_STORE = project_root() / "data" / "config" / "classroom_sessions.json"


def _read_classroom_sessions() -> list[dict[str, Any]]:
    try:
        value = json.loads(_CLASSROOM_SESSION_STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, dict) and item.get("id")] if isinstance(value, list) else []


def _write_classroom_sessions(items: list[dict[str, Any]]) -> None:
    _CLASSROOM_SESSION_STORE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _CLASSROOM_SESSION_STORE.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, _CLASSROOM_SESSION_STORE)


# Profiles remain supported for compatibility; both configured desktop agents
# use ``all`` and therefore receive the complete registered tool surface.
_MCP_PROFILE = os.getenv("PHYSICS_MCP_PROFILE", "all").strip().lower() or "all"
_PROFILE_BOUNDARY_INSTRUCTION = (
    "This is an external profile. Do not access, inspect, or modify the composition workbench. "
    "Search and curate questions without writing a workbench; use only the explicitly exposed external tools. "
    "If a user explicitly asks for workbench actions, provide a copyable instruction for the in-product AI assistant instead of requesting workbench MCP access. "
    if _MCP_PROFILE in {"external_study_sheet", "external_catalog_maintenance"}
    else "This is the in-product AI-assistant workbench profile. For requests to select questions and compose a paper, use the composition workbench by default. "
    if _MCP_PROFILE == "ai_assistant_workbench"
    else ""
)

server = MCPServer(
    name="physics_vault",
    title="Physics Vault Database",
    version="0.2.0",
    instructions=(
        _PROFILE_BOUNDARY_INSTRUCTION
        + "This server manages a local high-school physics question bank, review workspace, composition workbench, saved handouts, teaching projects, and background jobs. "
        "When the route or tool sequence is unclear, call get_workflow_guide; call mcp_system_health for readiness and integrity checks. "
        "Database boundaries are strict: canonical retrieval uses search tools; review/submitted/draft-task requests start with list_review_tasks or get_review_task; use database_boundary_report if uncertain. "
        "Canonical question bodies are not edited by metadata tools. Review tools write only review drafts unless a tool explicitly presents a canonical operation plan. "
        "For ordinary retrieval start with search_questions_compact, use search_questions_curated for a balanced shortlist, and fetch full records only for selected IDs. Named solution methods start with search_method_questions. "
        "Download managed question images only when figures must be inspected or reused. "
        "Keep workbench_draft, saved_handout, and teaching_project IDs distinct; never infer one document kind from another. "
        "All tools are visible, but visibility is not authorization to mutate. Respect dry_run defaults, confirmation flags, and plan_token requirements. A plan token binds execution to the previewed version; if the target changes, re-preview. Reusing a completed token is idempotent. "
        "For imports, merges, restores, publishing, replacement sync, canonical status changes, rollback, deletion, retry, cancel, and overwrite: preview first and execute only after explicit user confirmation. "
        "After review-draft repairs, validate again. After audited canonical metadata changes, report the audit batch and available rollback tool. "
        "Use the full stable IDs returned by tools in subsequent calls and report unresolved risks instead of claiming completion."
    ),
)

# A single service remains convenient for local development, while clients
# that support separate MCP entries can expose a narrower tool profile by
# setting PHYSICS_MCP_PROFILE. "all" preserves today's complete surface.
_TOOL_REGISTRY = default_tool_registry()
_mcp_server_tool = server.tool
_EXPOSED_TOOL_NAMES: set[str] = set()


def _profiled_mcp_tool(*args: Any, **kwargs: Any):
    decorator = _mcp_server_tool(*args, **kwargs)

    def register(func: Any) -> Any:
        tool_name = str(kwargs.get("name") or func.__name__)
        _TOOL_REGISTRY.bind(tool_name, func)
        if _MCP_PROFILE == "all" or tool_name in profile_tool_names(_MCP_PROFILE):
            registered = decorator(func)
            _EXPOSED_TOOL_NAMES.add(tool_name)
            return registered
        return func

    return register


server.tool = _profiled_mcp_tool  # type: ignore[method-assign]


def _validate_tool_registry() -> None:
    """Fail startup if the declarative catalogue and MCP exposure diverge."""
    _TOOL_REGISTRY.assert_all_bound()
    expected = _TOOL_REGISTRY.names()
    if _MCP_PROFILE != "all":
        expected = profile_tool_names(_MCP_PROFILE)
    exposed = set(_EXPOSED_TOOL_NAMES)
    if exposed != expected:
        missing = sorted(expected - exposed)
        unexpected = sorted(exposed - expected)
        raise RuntimeError(
            "MCP tool registry does not match exposed tools "
            f"(missing={missing}, unexpected={unexpected})"
        )


def _service_factory() -> MCPServiceFactory:
    return MCPServiceFactory(
        formal_db_path=_formal_db_path,
        review_db_path=_review_db_path,
    )


def _search_service() -> Any:
    return _service_factory().search()


def _import_service() -> Any:
    return _service_factory().import_pipeline()


def _task_center_service() -> Any:
    return _service_factory().task_center()


def _typst_export_service() -> Any:
    return _service_factory().typst_export()


def _paper_draft_service() -> Any:
    return _service_factory().paper_draft()


def _change_audit_service() -> Any:
    return _service_factory().change_audit()


def _metadata_management_service() -> Any:
    return _service_factory().metadata_management()


def _formal_db_path() -> Path:
    return default_db_path()


def _review_db_path() -> Path:
    review_path = default_review_db_path()
    review_path.parent.mkdir(parents=True, exist_ok=True)
    return review_path


def _database_runtime() -> DatabaseRuntime:
    return DatabaseRuntime(
        formal_db_path=_formal_db_path,
        review_db_path=_review_db_path,
        ensure_review_schema=_ensure_review_db_schema,
    )


def _connect_formal_read_db() -> sqlite3.Connection:
    return _database_runtime().connect_formal_read()


def _connect_formal_write_db() -> sqlite3.Connection:
    return _database_runtime().connect_formal_write()


def _connect_review_db() -> sqlite3.Connection:
    return _database_runtime().connect_review()


_MCP_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg"}


def _mcp_download_directory(destination_subdir: str | None) -> Path | None:
    """Resolve an agent download directory without permitting arbitrary writes."""
    raw_subdir = str(destination_subdir or "").strip().replace("\\", "/")
    relative = Path(raw_subdir) if raw_subdir else Path()
    if relative.is_absolute() or any(part == ".." for part in relative.parts):
        return None
    base = (project_root() / "data" / "mcp-downloads").resolve()
    target = (base / relative).resolve()
    return target if target == base or base in target.parents else None


def _resolve_managed_image_path(file_path: str) -> Path | None:
    """Resolve a database image path while keeping MCP reads in managed project data."""
    raw_path = str(file_path or "").strip()
    if not raw_path:
        return None
    root = project_root().resolve()
    candidate = Path(raw_path).expanduser()
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    managed_roots = ((root / "data" / "assets").resolve(), (root / "data" / "import-batches").resolve())
    if not target.is_file() or target.suffix.lower() not in _MCP_IMAGE_SUFFIXES:
        return None
    return target if any(target == managed or managed in target.parents for managed in managed_roots) else None


def _decode_json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _question_image_records(question_id: str) -> list[dict[str, str]]:
    """Return managed assets bound to a question, with legacy figure metadata as fallback."""
    records: list[dict[str, str]] = []
    try:
        with _connect_formal_read_db() as conn:
            has_image_tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('image_assets', 'question_assets')"
            ).fetchone()[0] == 2
            if has_image_tables:
                rows = conn.execute(
                    """
                    SELECT ia.asset_id, ia.filename, ia.file_path
                    FROM question_assets qa
                    JOIN image_assets ia ON ia.asset_id = qa.asset_id
                    WHERE qa.question_id = ?
                    ORDER BY qa.sort_order, ia.asset_id
                    """,
                    (question_id,),
                ).fetchall()
                if not rows:
                    rows = conn.execute(
                        """
                        SELECT asset_id, filename, file_path
                        FROM image_assets
                        WHERE question_id = ?
                        ORDER BY asset_id
                        """,
                        (question_id,),
                    ).fetchall()
                records.extend(
                    {
                        "asset_id": str(row["asset_id"] or ""),
                        "filename": str(row["filename"] or ""),
                        "file_path": str(row["file_path"] or ""),
                    }
                    for row in rows
                )

            if not records:
                row = conn.execute(
                    """
                    SELECT figures_json, image_asset_ids_json, image_filenames_json
                    FROM question_text_index WHERE question_id = ?
                    """,
                    (question_id,),
                ).fetchone()
                if row:
                    figures = _decode_json_list(row["figures_json"])
                    for index, figure in enumerate(figures, start=1):
                        if not isinstance(figure, dict):
                            continue
                        file_path = str(figure.get("local_path") or figure.get("file_path") or figure.get("path") or "")
                        if file_path:
                            records.append({
                                "asset_id": str(figure.get("asset_id") or figure.get("fig_uuid") or f"figure-{index}"),
                                "filename": Path(file_path).name,
                                "file_path": file_path,
                            })
    except sqlite3.Error:
        return []
    return records


def _resolve_review_task_id(task_id: str) -> str | None:
    """Resolve an exact task id or a unique short UUID prefix."""
    tid = str(task_id or "").strip()
    if not tid:
        return None
    with _connect_review_db() as conn:
        row = conn.execute(
            "SELECT task_id FROM import_pipeline_tasks WHERE task_id = ?",
            (tid,),
        ).fetchone()
        if row is not None:
            return str(row["task_id"])
        rows = conn.execute(
            "SELECT task_id FROM import_pipeline_tasks WHERE task_id LIKE ? ORDER BY updated_at DESC LIMIT 2",
            (f"{tid}%",),
        ).fetchall()
    if len(rows) == 1:
        return str(rows[0]["task_id"])
    return None


def _load_review_task(task_id: str) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """统一读取审核任务，并集中处理空 ID、短 ID、缺表和任务不存在。"""
    requested = str(task_id or "").strip()
    if not requested:
        return None, None, _tool_error("INVALID_ARGUMENT", "task_id 不能为空。", field="task_id")

    resolved = _resolve_review_task_id(requested)
    if resolved is None:
        return None, None, {
            "ok": False,
            "status": "missing",
            "task_id": requested,
            "error": "校对任务不存在，或任务号前缀不唯一。",
        }

    with _connect_review_db() as conn:
        if not _table_exists(conn, "import_pipeline_tasks"):
            return None, None, {
                "ok": False,
                "table_missing": True,
                "error": "import_pipeline_tasks 表不存在。",
            }
        row = conn.execute(
            """
            SELECT task_id, task_type, status, created_at, updated_at,
                   input_summary_json, result_json, error
            FROM import_pipeline_tasks
            WHERE task_id = ?
            """,
            (resolved,),
        ).fetchone()
    if row is None:
        return None, None, {
            "ok": False,
            "status": "missing",
            "task_id": resolved,
            "error": "校对任务不存在。",
        }
    return resolved, dict(row), None


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


def _ensure_review_queue_outbox_schema(conn: sqlite3.Connection) -> None:
    """Persist cross-database review-queue deliveries for safe retries.

    A canonical status update and an insert into the review database cannot share
    one SQLite transaction.  The outbox is committed with the canonical update,
    then delivered separately and retried by ``reconcile_review_queue_outbox``.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_queue_outbox (
            operation_id TEXT PRIMARY KEY,
            review_id TEXT NOT NULL UNIQUE,
            question_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            audit_batch_id TEXT,
            delivery_status TEXT NOT NULL DEFAULT 'pending',
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            delivered_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_queue_outbox_pending
        ON review_queue_outbox(delivery_status, created_at)
        """
    )


def _deliver_review_queue_outbox(operation_id: str) -> dict[str, Any]:
    """Deliver one durable outbox item to the review DB without duplicating it."""
    with _connect_formal_write_db() as conn:
        _ensure_review_queue_outbox_schema(conn)
        row = conn.execute(
            """
            SELECT operation_id, review_id, question_id, reason, payload_json,
                   audit_batch_id, delivery_status, delivery_attempts, last_error
            FROM review_queue_outbox WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        return _tool_error("OUTBOX_OPERATION_NOT_FOUND", "审核队列投递操作不存在。", field="operation_id")

    if row["delivery_status"] == "delivered":
        return {
            "ok": True,
            "operation_id": operation_id,
            "delivery_status": "delivered",
            "already_delivered": True,
            "audit_batch_id": row["audit_batch_id"],
        }
    if row["delivery_status"] == "cancelled":
        return {
            "ok": True,
            "operation_id": operation_id,
            "delivery_status": "cancelled",
            "skipped": True,
            "audit_batch_id": row["audit_batch_id"],
        }

    try:
        with _connect_review_db() as review_conn:
            review_conn.execute(
                """
                INSERT OR REPLACE INTO review_queue (
                    review_id, entity_type, entity_id, queue_type, status,
                    priority, reason, payload_json, created_at, updated_at
                ) VALUES (?, 'question', ?, 'rework', 'pending', 5, ?, ?,
                          CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (row["review_id"], row["question_id"], row["reason"], row["payload_json"]),
            )
            review_conn.commit()
    except sqlite3.Error as exc:
        with _connect_formal_write_db() as conn:
            _ensure_review_queue_outbox_schema(conn)
            conn.execute(
                """
                UPDATE review_queue_outbox
                SET delivery_attempts = delivery_attempts + 1, last_error = ?
                WHERE operation_id = ?
                """,
                (str(exc), operation_id),
            )
            conn.commit()
        return {
            "ok": False,
            "operation_id": operation_id,
            "delivery_status": "pending",
            "error_info": {
                "code": "REVIEW_QUEUE_DELIVERY_PENDING",
                "message": "正式库更新已保存，但审核队列暂未写入；可稍后重试对账。",
                "retryable": True,
                "details": {},
            },
        }

    with _connect_formal_write_db() as conn:
        _ensure_review_queue_outbox_schema(conn)
        conn.execute(
            """
            UPDATE review_queue_outbox
            SET delivery_status = 'delivered', delivery_attempts = delivery_attempts + 1,
                last_error = NULL, delivered_at = CURRENT_TIMESTAMP
            WHERE operation_id = ?
            """,
            (operation_id,),
        )
        conn.commit()
    return {
        "ok": True,
        "operation_id": operation_id,
        "delivery_status": "delivered",
        "audit_batch_id": row["audit_batch_id"],
    }


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
    return clean_args(args)


def _tool_error(
    code: str,
    message: str,
    *,
    field: str | None = None,
    retryable: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return tool_error(code, message, field=field, retryable=retryable, **extra)


def _operation_plan_payload(
    *,
    action: str,
    targets: list[dict[str, Any]],
    summary: str,
    warnings: list[str] | None = None,
    version_snapshot: Any = None,
    reversible: bool,
) -> dict[str, Any]:
    """Attach the SAFE-201 contract without changing a legacy tool response."""
    return build_operation_plan(
        action=action,
        targets=targets,
        summary=summary,
        warnings=warnings,
        version_snapshot=version_snapshot,
        reversible=reversible,
    ).model_dump(mode="json")


def _mcp_operation_plan_service() -> OperationPlanService:
    """Persist MCP confirmation plans beside, but not inside, the canonical DB."""
    plan_db = _formal_db_path().parent / "mcp_operation_plans.sqlite3"
    return OperationPlanService(OperationPlanRepository(plan_db))


def _persisted_operation_plan_payload(
    *,
    action: str,
    targets: list[dict[str, Any]],
    summary: str,
    warnings: list[str] | None = None,
    version_snapshot: Any = None,
    reversible: bool,
) -> dict[str, Any]:
    plan = build_operation_plan(
        action=action,
        targets=targets,
        summary=summary,
        warnings=warnings,
        version_snapshot=version_snapshot,
        reversible=reversible,
    )
    _mcp_operation_plan_service().save_preview(plan)
    return plan.model_dump(mode="json")


def _execute_persisted_operation(
    plan_token: str | None,
    *,
    action: str,
    version_snapshot_reader: Callable[[], Any],
    executor: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    token = str(plan_token or "").strip()
    if not token:
        return _tool_error(
            "PLAN_TOKEN_REQUIRED",
            "该操作需要先预览并取得 plan_token，再由用户确认后执行。",
            field="plan_token",
        )

    def _version_reader(plan: Any) -> str:
        if str(plan.action) != action:
            raise OperationPlanVersionConflict(
                f"plan token action mismatch: expected {action}, got {plan.action}"
            )
        return snapshot_version(version_snapshot_reader())

    try:
        execution = _mcp_operation_plan_service().execute(
            token,
            version_reader=_version_reader,
            executor=lambda _plan: executor(),
        )
    except OperationPlanVersionConflict as exc:
        return _tool_error(
            "OPERATION_PLAN_VERSION_CONFLICT",
            f"预览后目标内容已变化，请重新预览：{exc}",
            field="plan_token",
        )
    except OperationPlanError as exc:
        return _tool_error("OPERATION_PLAN_NOT_FOUND", str(exc), field="plan_token")
    if execution.status != "completed":
        return _tool_error(
            "OPERATION_PLAN_NOT_EXECUTED",
            execution.error or f"操作计划状态为 {execution.status}。",
            field="plan_token",
            operation_id=execution.operation_id,
            status=execution.status,
        )
    payload = dict(execution.result) if isinstance(execution.result, dict) else {"result": execution.result}
    if "operation_id" in payload:
        payload["plan_operation_id"] = execution.operation_id
    else:
        payload["operation_id"] = execution.operation_id
    payload["idempotent"] = execution.idempotent
    return payload


def _question_operation_targets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert preview rows to stable operation-plan target descriptors."""
    return [
        {
            "type": "question",
            "id": str(item["question_id"]),
            "label": str(item.get("title") or "").strip() or None,
        }
        for item in items
        if item.get("status") == "changed" and str(item.get("question_id") or "").strip()
    ]


class ReviewTaskConflictError(RuntimeError):
    """Raised when a review draft changed after the caller read it."""

    def __init__(self, task_id: str, expected: str, current: str) -> None:
        super().__init__(f"校对任务 {task_id} 已被其他操作修改。")
        self.task_id = task_id
        self.expected = expected
        self.current = current


def _format_spec_diff(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    *,
    before_template_id: str | None = None,
    after_template_id: str | None = None,
) -> dict[str, Any]:
    """Summarize format changes without returning a large before/after payload."""
    previous = before if isinstance(before, dict) else {}
    sections = ("styleConfig", "headerFooter", "contentStyles", "output", "rules")
    changed_fields: dict[str, list[str]] = {}
    for section in sections:
        previous_section = previous.get(section) if isinstance(previous.get(section), dict) else {}
        next_section = after.get(section) if isinstance(after.get(section), dict) else {}
        fields = sorted(
            key
            for key in set(previous_section) | set(next_section)
            if previous_section.get(key) != next_section.get(key)
        )
        if fields:
            changed_fields[section] = fields
    return {
        "changed_sections": sorted(changed_fields),
        "changed_fields": changed_fields,
        "before_template_id": before_template_id,
        "after_template_id": after_template_id,
    }


_REVIEW_INTENT_RE = re.compile(
    r"(校对中心|待校对|审核任务|审核队列|送审|已送审|草稿|回炉|复核|review center|submitted|draft)",
    re.IGNORECASE,
)
_FORMAL_INTENT_RE = re.compile(r"(正式库|正式题库|标准库|已入库|canonical|approved)", re.IGNORECASE)


def _looks_like_review_intent(text: str | None) -> bool:
    value = str(text or "")
    return bool(_REVIEW_INTENT_RE.search(value)) and not bool(_FORMAL_INTENT_RE.search(value))


def _legacy_list_teaching_projects(limit: int = 50) -> dict[str, Any]:
    """列出教学项目及讲义、课件、课堂产物状态。只读。"""
    return {"ok": True, "document_kind": "teaching_project", "items": _list_teaching_projects(limit)}


def _legacy_get_teaching_project(project_id: str) -> dict[str, Any]:
    """读取一个教学项目的内容源、产物状态和发布快照。只读。"""
    project = _get_teaching_project(project_id)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    return {"ok": True, **project, "document_kind": "teaching_project"}


def _legacy_get_teaching_project_status(project_id: str) -> dict[str, Any]:
    """读取教学项目的内容版本、讲义/课件状态和发布版本号。"""
    project = _get_teaching_project(project_id)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    result: dict[str, Any] = {
        "project_id": project_id,
        "title": project.get("title"),
        "project_type": project.get("projectType"),
        "content_revision": project.get("contentRevision"),
        "status": project.get("status", "draft"),
    }
    for key in ("handout", "slides"):
        artifact = project.get(key) if isinstance(project.get(key), dict) else {}
        published = artifact.get("publishedSnapshot") if isinstance(artifact.get("publishedSnapshot"), dict) else {}
        result[key] = {
            "status": artifact.get("status", "draft"),
            "source_revision": artifact.get("sourceRevision"),
            "published_version": published.get("version"),
            "published_at": published.get("publishedAt"),
        }
    return {"ok": True, "document_kind": "teaching_project_status", "status": result}


def _legacy_duplicate_teaching_project(project_id: str, title: str | None = None) -> dict[str, Any]:
    """复制教学项目；副本会重置为草稿并清除已发布产物快照。"""
    project = _duplicate_teaching_project(project_id, title=title)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    return {"ok": True, **project, "document_kind": "teaching_project"}


def _legacy_publish_teaching_artifact(
    project_id: str,
    artifact: Literal["handout", "slides"] = "slides",
    confirmed: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """发布教学产物；执行必须使用预览返回的、带版本约束的 plan_token。"""
    project = _get_teaching_project(project_id)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    current = project.get(artifact) if isinstance(project.get(artifact), dict) else None
    if not current:
        return _tool_error("ARTIFACT_NOT_FOUND", f"项目没有{artifact}产物。", field="artifact")
    plan = {
        "project_id": project_id,
        "artifact": artifact,
        "status_before": current.get("status", "draft"),
        "source_revision": current.get("sourceRevision"),
        "requires_confirmation": True,
        "message": "将创建新的不可变发布快照，课堂将只读取课件发布快照。",
    }
    def version_snapshot() -> dict[str, Any]:
        latest = _get_teaching_project(project_id) or {}
        latest_artifact = latest.get(artifact) if isinstance(latest.get(artifact), dict) else {}
        published = latest_artifact.get("publishedSnapshot") if isinstance(latest_artifact.get("publishedSnapshot"), dict) else {}
        return {
            "project_id": project_id,
            "project_updated_at": latest.get("updatedAt"),
            "content_revision": latest.get("contentRevision"),
            "artifact": artifact,
            "artifact_status": latest_artifact.get("status"),
            "source_revision": latest_artifact.get("sourceRevision"),
            "published_version": published.get("version"),
        }
    if not confirmed:
        operation_plan = _persisted_operation_plan_payload(
            action="teaching_project.publish_artifact",
            targets=[{"type": "teaching_project_artifact", "id": f"{project_id}:{artifact}", "label": artifact}],
            summary=f"发布教学项目 {project_id} 的 {artifact} 产物并创建不可变快照。",
            warnings=["执行前会校验项目与产物版本；预览后发生变化时必须重新预览。"],
            version_snapshot=version_snapshot(),
            reversible=True,
        )
        return {"ok": True, "dry_run": True, "plan": plan, "operation_plan": operation_plan, "plan_token": operation_plan["operation_id"]}

    def execute_publish() -> dict[str, Any]:
        latest = _get_teaching_project(project_id)
        if not latest:
            return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
        latest_artifact = latest.get(artifact) if isinstance(latest.get(artifact), dict) else None
        if not latest_artifact:
            return _tool_error("ARTIFACT_NOT_FOUND", f"项目没有{artifact}产物。", field="artifact")
        now = datetime.now(timezone.utc).isoformat()
        version = int((latest_artifact.get("publishedSnapshot") or {}).get("version") or 0) + 1
        snapshot = json.loads(json.dumps({key: value for key, value in latest_artifact.items() if key not in {"publishedSnapshot", "updatedAt", "status"}}))
        snapshot["publishedAt"] = now
        snapshot["version"] = version
        if artifact == "slides":
            lesson_package = (latest_artifact.get("publishedSnapshot") or {}).get("lessonPackage")
            if not isinstance(lesson_package, dict):
                return _tool_error("PUBLISHED_SOURCE_REQUIRED", "课件发布需要完整的教学包快照，请先在课件页面发布一次。", field="artifact")
            snapshot["lessonPackage"] = lesson_package
        latest_artifact["publishedSnapshot"] = snapshot
        latest_artifact["status"] = "published"
        latest_artifact["updatedAt"] = now
        try:
            saved = _save_teaching_project(latest, base_updated_at=latest.get("updatedAt"))
        except TeachingProjectConflictError as exc:
            return _tool_error("PROJECT_REVISION_CONFLICT", str(exc), field="project_id")
        return {"ok": True, "dry_run": False, "project": saved, "published_version": version}

    return _execute_persisted_operation(
        plan_token,
        action="teaching_project.publish_artifact",
        version_snapshot_reader=version_snapshot,
        executor=execute_publish,
    )


def _legacy_preflight_teaching_handout(project_id: str, use_published: bool = False) -> dict[str, Any]:
    """检查讲义是否具备可发布/可导出的基本条件，并返回结构化风险。"""
    project = _get_teaching_project(project_id)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    artifact = project.get("handout") if isinstance(project.get("handout"), dict) else {}
    snapshot = artifact.get("publishedSnapshot") if use_published else None
    source = snapshot if isinstance(snapshot, dict) else artifact
    config = source.get("config") if isinstance(source.get("config"), dict) else {}
    risks: list[dict[str, Any]] = []
    if artifact.get("status") in {"stale", "changed_after_publish"} and not use_published:
        risks.append({"severity": "warning", "code": "STALE_SOURCE", "message": "讲义内容源已变化，当前草稿需要重新分页并发布。"})
    if not str(config.get("title") or "").strip():
        risks.append({"severity": "warning", "code": "EMPTY_TITLE", "message": "讲义标题为空。"})
    if config.get("headerFooter", {}).get("footerEnabled") and not str(config.get("headerFooter", {}).get("footerText") or "").strip():
        risks.append({"severity": "warning", "code": "EMPTY_FOOTER", "message": "页脚已启用但页脚文字为空。"})
    if config.get("styleConfig", {}).get("pageSize") not in {None, "A4", "A3"}:
        risks.append({"severity": "danger", "code": "INVALID_PAGE_SIZE", "message": "页面尺寸不是 A4 或 A3。"})
    return {
        "ok": True,
        "document_kind": "teaching_handout_preflight",
        "project_id": project_id,
        "use_published": use_published,
        "source_revision": source.get("sourceRevision"),
        "published_version": (artifact.get("publishedSnapshot") or {}).get("version"),
        "risk_count": len(risks),
        "risks": risks,
        "ready": not any(item["severity"] == "danger" for item in risks),
    }


def _legacy_sync_teaching_slides(
    project_id: str,
    strategy: Literal["preserve_manual", "replace"] = "preserve_manual",
    confirmed: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """同步课件与项目内容版本；默认只返回差异计划，避免误覆盖手工页面。"""
    project = _get_teaching_project(project_id)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    artifact = project.get("slides") if isinstance(project.get("slides"), dict) else {}
    current_deck = artifact.get("deck") if isinstance(artifact.get("deck"), dict) else {}
    generated_deck = artifact.get("generatedDeck") if isinstance(artifact.get("generatedDeck"), dict) else None
    current_pages = current_deck.get("pages") if isinstance(current_deck.get("pages"), list) else []
    generated_pages = generated_deck.get("pages") if isinstance(generated_deck, dict) and isinstance(generated_deck.get("pages"), list) else []
    page_ids = {str(item.get("id")) for item in current_pages if isinstance(item, dict)}
    generated_ids = {str(item.get("id")) for item in generated_pages if isinstance(item, dict)}
    plan = {
        "project_id": project_id,
        "strategy": strategy,
        "source_revision": project.get("contentRevision"),
        "current_revision": artifact.get("sourceRevision"),
        "new_pages": sorted(generated_ids - page_ids),
        "removed_pages": sorted(page_ids - generated_ids),
        "manual_pages_preserved": strategy == "preserve_manual",
        "requires_confirmation": True,
    }
    def version_snapshot() -> dict[str, Any]:
        latest = _get_teaching_project(project_id) or {}
        latest_artifact = latest.get("slides") if isinstance(latest.get("slides"), dict) else {}
        latest_deck = latest_artifact.get("deck") if isinstance(latest_artifact.get("deck"), dict) else {}
        latest_generated = latest_artifact.get("generatedDeck") if isinstance(latest_artifact.get("generatedDeck"), dict) else {}
        return {
            "project_id": project_id,
            "project_updated_at": latest.get("updatedAt"),
            "content_revision": latest.get("contentRevision"),
            "artifact_source_revision": latest_artifact.get("sourceRevision"),
            "strategy": strategy,
            "current_page_ids": [str(item.get("id")) for item in latest_deck.get("pages", []) if isinstance(item, dict)],
            "generated_page_ids": [str(item.get("id")) for item in latest_generated.get("pages", []) if isinstance(item, dict)],
        }
    if not confirmed:
        operation_plan = _persisted_operation_plan_payload(
            action="teaching_project.sync_slides",
            targets=[{"type": "teaching_project_slides", "id": project_id, "label": strategy}],
            summary=f"按 {strategy} 策略同步教学项目 {project_id} 的课件。",
            warnings=["replace 会覆盖当前生成页；执行前会再次校验页面与项目版本。"],
            version_snapshot=version_snapshot(),
            reversible=True,
        )
        return {"ok": True, "dry_run": True, "plan": plan, "operation_plan": operation_plan, "plan_token": operation_plan["operation_id"]}

    def execute_sync() -> dict[str, Any]:
        latest = _get_teaching_project(project_id)
        if not latest:
            return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
        latest_artifact = latest.get("slides") if isinstance(latest.get("slides"), dict) else {}
        latest_generated = latest_artifact.get("generatedDeck") if isinstance(latest_artifact.get("generatedDeck"), dict) else None
        if strategy == "preserve_manual":
            return {"ok": True, "dry_run": False, "applied": False, "plan": plan, "message": "保留手工页面策略需要在网页端执行差异合并，本次仅记录同步意图。"}
        if not latest_generated:
            return _tool_error("GENERATED_DECK_NOT_FOUND", "项目没有可用于替换的生成课件快照，请先在课件页同步内容。", field="project_id")
        now = datetime.now(timezone.utc).isoformat()
        latest_artifact["deck"] = latest_generated
        latest_artifact["sourceRevision"] = latest.get("contentRevision")
        latest_artifact["status"] = "ready"
        latest_artifact["updatedAt"] = now
        try:
            saved = _save_teaching_project(latest, base_updated_at=latest.get("updatedAt"))
        except TeachingProjectConflictError as exc:
            return _tool_error("PROJECT_REVISION_CONFLICT", str(exc), field="project_id")
        return {"ok": True, "dry_run": False, "applied": True, "project": saved, "plan": plan}

    return _execute_persisted_operation(
        plan_token,
        action="teaching_project.sync_slides",
        version_snapshot_reader=version_snapshot,
        executor=execute_sync,
    )


def _legacy_start_classroom_session(project_id: str) -> dict[str, Any]:
    """从已发布课件创建一个持久化课堂会话。"""
    project = _get_teaching_project(project_id)
    if not project:
        return _tool_error("TEACHING_PROJECT_NOT_FOUND", f"教学项目不存在：{project_id}。", field="project_id")
    published = project.get("slides", {}).get("publishedSnapshot") if isinstance(project.get("slides"), dict) else None
    if not isinstance(published, dict):
        return _tool_error("PUBLISHED_SLIDES_REQUIRED", "课堂只能从已发布课件启动。", field="project_id")
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "id": f"classroom-{project_id}-{uuid.uuid4().hex[:10]}",
        "projectId": project_id,
        "publishedVersion": published.get("version"),
        "currentIndex": 0,
        "displayMode": "stem_only",
        "revealStep": 0,
        "teacherNotes": "",
        "annotations": {},
        "status": "active",
        "startedAt": now,
        "updatedAt": now,
    }
    sessions = _read_classroom_sessions()
    _write_classroom_sessions([*sessions, session])
    return {"ok": True, "document_kind": "classroom_session", "session": session}


def _legacy_get_classroom_session(session_id: str) -> dict[str, Any]:
    """读取课堂会话进度、教师备注和页面批注。"""
    session = next((item for item in _read_classroom_sessions() if str(item.get("id")) == str(session_id)), None)
    if not session:
        return _tool_error("CLASSROOM_SESSION_NOT_FOUND", f"课堂会话不存在：{session_id}。", field="session_id")
    return {"ok": True, "document_kind": "classroom_session", "session": session}


def _legacy_update_classroom_session(
    session_id: str,
    current_index: int | None = None,
    display_mode: Literal["stem_only", "stem_answer", "full"] | None = None,
    reveal_step: int | None = None,
    teacher_notes: str | None = None,
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """更新课堂进度、授课显示模式、教师备注和页面批注。"""
    sessions = _read_classroom_sessions()
    index = next((idx for idx, item in enumerate(sessions) if str(item.get("id")) == str(session_id)), None)
    if index is None:
        return _tool_error("CLASSROOM_SESSION_NOT_FOUND", f"课堂会话不存在：{session_id}。", field="session_id")
    session = dict(sessions[index])
    if current_index is not None: session["currentIndex"] = max(0, int(current_index))
    if display_mode is not None: session["displayMode"] = display_mode
    if reveal_step is not None: session["revealStep"] = max(0, int(reveal_step))
    if teacher_notes is not None: session["teacherNotes"] = teacher_notes
    if annotations is not None: session["annotations"] = annotations
    session["updatedAt"] = datetime.now(timezone.utc).isoformat()
    sessions[index] = session
    _write_classroom_sessions(sessions)
    return {"ok": True, "document_kind": "classroom_session", "session": session}


def _legacy_end_classroom_session(session_id: str) -> dict[str, Any]:
    """结束课堂会话并保留复盘所需的最终状态。"""
    sessions = _read_classroom_sessions()
    index = next((idx for idx, item in enumerate(sessions) if str(item.get("id")) == str(session_id)), None)
    if index is None:
        return _tool_error("CLASSROOM_SESSION_NOT_FOUND", f"课堂会话不存在：{session_id}。", field="session_id")
    session = dict(sessions[index])
    session["status"] = "ended"
    session["endedAt"] = datetime.now(timezone.utc).isoformat()
    session["updatedAt"] = session["endedAt"]
    sessions[index] = session
    _write_classroom_sessions(sessions)
    return {"ok": True, "document_kind": "classroom_session", "session": session}


def _legacy_list_filter_facets() -> dict[str, Any]:
    """列出题库可用筛选项，包括年份、模块、题型、难度、状态和知识点层级取值。"""
    return _dump_model(_search_service().get_facets())


def _legacy_search_questions(
    query: str | None = None,
    search_mode: Literal["browse", "strict", "hybrid", "similar", "comprehensive"] = "hybrid",
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
    """按关键词、题型、难度、知识点、年份、来源等条件检索正式题库。

    hybrid 默认合并 embedding 语义召回、BM25 关键词召回、方法结构召回和 rerank 精排；
    comprehensive 模式还会扫描题干、解析、知识树、旧 module/topic 字段和历史标签，
    并为“配速法”等解题方法返回 explicit/structural/related 分级证据。
    只读；不要用本工具定位送审/校对草稿。
    """
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
    if clean.get("search_mode") == "comprehensive":
        if not clean.get("query"):
            return _tool_error("INVALID_ARGUMENT", "comprehensive 模式需要 query。", field="query")
        return _search_questions_comprehensive(
            query=str(clean["query"]),
            question_type=clean.get("question_type"),
            difficulty=clean.get("difficulty"),
            status=clean.get("status"),
            module=clean.get("module"),
            topic1_id=clean.get("topic1_id"),
            topic2_id=clean.get("topic2_id"),
            topic3_id=clean.get("topic3_id"),
            topic2=clean.get("topic2"),
            topic3=clean.get("topic3"),
            limit=int(clean["limit"]),
            offset=int(clean["offset"]),
            year=clean.get("year"),
            region=clean.get("region"),
            exam_type=clean.get("exam_type"),
            has_media=clean.get("has_media"),
        )
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


def _compact_question_card(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return the smallest useful search card without changing local ranking."""
    title = _truncate_search_text(item.get("title") or item.get("canonical_title"), 140)
    knowledge_point = _truncate_search_text(item.get("knowledge_point"), 100)
    source = _truncate_search_text(item.get("source"), 100)
    return {
        "question_id": item.get("question_id"),
        "title": title,
        "question_type": item.get("question_type"),
        "difficulty": item.get("difficulty"),
        "knowledge_point": knowledge_point,
        "source": source,
        "year": item.get("year"),
        "score": item.get("score"),
        "has_media": bool(item.get("has_media")),
        "image_count": int(item.get("image_count") or 0),
    }


def _compact_search_response(result: Mapping[str, Any]) -> dict[str, Any]:
    """Project a full search result into cards; search, recall and rerank stay intact."""
    items = result.get("items") if isinstance(result.get("items"), list) else []
    return {
        "items": [_compact_question_card(item) for item in items if isinstance(item, Mapping)],
        "total": int(result.get("total") or 0),
        "limit": int(result.get("limit") or len(items)),
        "offset": int(result.get("offset") or 0),
        "search_mode": result.get("search_mode"),
        "database_scope": result.get("database_scope", "canonical_read_only"),
        "next_tool": "get_questions_by_ids",
        "message": "已完成完整本地检索和排序；此响应只省略未选题目的题干、答案、解析、选项与图片详情。",
    }


def _legacy_search_questions_compact(
    query: str | None = None,
    search_mode: Literal["browse", "strict", "hybrid", "similar", "comprehensive"] = "hybrid",
    question_type: str | None = None,
    difficulty: str | None = None,
    year: int | None = None,
    topic3_id: str | None = None,
    limit: int = 12,
    offset: int = 0,
) -> dict[str, Any]:
    """完整检索和精排后，仅返回紧凑题目卡；用 get_questions_by_ids 按需取全文。"""
    result = _legacy_search_questions(
        query=query,
        search_mode=search_mode,
        question_type=question_type,
        difficulty=difficulty,
        year=year,
        topic3_id=topic3_id,
        limit=min(max(int(limit or 12), 1), 50),
        offset=max(int(offset or 0), 0),
    )
    if result.get("misrouted") or result.get("ok") is False:
        return result
    return _compact_search_response(result)


def _legacy_search_questions_curated(
    query: str,
    target_count: int = 10,
    candidate_limit: int = 50,
    search_mode: Literal["strict", "hybrid", "comprehensive"] = "hybrid",
    question_type: str | None = None,
    difficulty: str | None = None,
    year: int | None = None,
    topic3_id: str | None = None,
) -> dict[str, Any]:
    """在服务端完成检索、精排与题型/难度/来源均衡精选；不写入任何工作台。"""
    clean_query = str(query or "").strip()
    if not clean_query:
        return _tool_error("INVALID_ARGUMENT", "query 不能为空。", field="query")
    searched = _legacy_search_questions(
        query=clean_query,
        search_mode=search_mode,
        question_type=question_type,
        difficulty=difficulty,
        year=year,
        topic3_id=topic3_id,
        limit=min(max(int(candidate_limit or 50), 1), 50),
        offset=0,
    )
    if searched.get("misrouted") or searched.get("ok") is False:
        return searched
    candidates = [item for item in searched.get("items") or [] if isinstance(item, Mapping)]
    count = min(max(int(target_count or 10), 1), 30)
    selected = _select_balanced_composition_candidates(candidates, count, clean_query)
    return {
        "items": [_compact_question_card(item) for item in selected],
        "selected_question_ids": [str(item.get("question_id")) for item in selected],
        "candidate_count": len(candidates),
        "total_matches": int(searched.get("total") or 0),
        "selection_policy": "在完整本地检索和精排结果内，优先平衡来源、题型与难度；不写入组卷工作台。",
        "next_tool": "get_questions_by_ids",
        "database_scope": "canonical_read_only",
    }


def _legacy_download_question_images(
    question_id: str,
    destination_subdir: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """下载某道正式题目关联的图片到本地受管目录，供智能体读图、OCR 或制作素材。"""
    clean_question_id = str(question_id or "").strip()
    if not clean_question_id:
        return _tool_error("INVALID_ARGUMENT", "question_id 不能为空。", field="question_id")
    target_dir = _mcp_download_directory(destination_subdir)
    if target_dir is None:
        return _tool_error(
            "INVALID_ARGUMENT",
            "destination_subdir 只能是 data/mcp-downloads 下的相对目录，不能包含 .. 或绝对路径。",
            field="destination_subdir",
        )

    records = _question_image_records(clean_question_id)
    if not records:
        return {
            "ok": True,
            "question_id": clean_question_id,
            "download_dir": str(target_dir),
            "downloaded_count": 0,
            "images": [],
            "message": "该题没有可下载的受管图片素材。",
        }

    target_dir.mkdir(parents=True, exist_ok=True)
    images: list[dict[str, Any]] = []
    for position, record in enumerate(records, start=1):
        source = _resolve_managed_image_path(record["file_path"])
        asset_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", record["asset_id"] or f"image-{position}").strip("._") or f"image-{position}"
        filename = Path(record["filename"] or source.name if source else "image").name
        target = target_dir / f"{position:02d}_{asset_id}_{filename}"
        if source is None:
            images.append({
                "asset_id": record["asset_id"],
                "status": "unavailable",
                "message": "图片文件不存在、格式不受支持，或不在受管素材目录。",
            })
            continue
        try:
            reused_existing_file = target.exists() and not overwrite
            if not reused_existing_file:
                temporary = target.with_suffix(f"{target.suffix}.{uuid.uuid4().hex}.tmp")
                shutil.copyfile(source, temporary)
                os.replace(temporary, target)
            images.append({
                "asset_id": record["asset_id"],
                "filename": source.name,
                "local_path": str(target),
                "source_path": str(source),
                "status": "downloaded",
                "reused_existing_file": reused_existing_file,
            })
        except OSError as exc:
            images.append({
                "asset_id": record["asset_id"],
                "status": "failed",
                "message": str(exc),
            })

    downloaded = [item for item in images if item["status"] == "downloaded"]
    return {
        "ok": bool(downloaded) or not images,
        "question_id": clean_question_id,
        "download_dir": str(target_dir),
        "downloaded_count": len(downloaded),
        "unavailable_count": len(images) - len(downloaded),
        "images": images,
        "next_step": "对 returned local_path 使用读图、OCR 或附件能力；若有 unavailable 项，先核对题目图片绑定。",
    }


_TOPIC_QUERY_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("匀变速", "匀加速", "匀减速", "变速直线", "运动学"),
        ("匀变速直线运动", "匀加速直线运动", "匀减速直线运动", "追及", "相遇", "上抛", "竖直上抛", "刹车", "制动", "自由落体", "速度时间图像", "v-t图像"),
    ),
    (
        ("追及", "相遇"),
        ("追及", "相遇", "匀变速直线运动", "速度时间图像"),
    ),
    (
        ("上抛", "竖直上抛"),
        ("上抛", "竖直上抛", "匀变速直线运动", "自由落体"),
    ),
    (
        ("刹车", "制动"),
        ("刹车", "制动", "匀减速直线运动", "匀变速直线运动"),
    ),
)


def _comprehensive_query_terms(query: str) -> list[str]:
    """Build a small, explainable topic expansion without hiding exact matches."""
    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    method_intent = detect_method_intent(clean_query)
    if method_intent is not None:
        # Named solution methods are teaching terms, not ordinary topics.  Do not
        # mix the generic topic/token expansion into this branch: a query such as
        # "电磁感应 配速法" used to inherit high-frequency terms such as 法拉第 and
        # 楞次定律, which drowned out the actual method signature.
        return list(
            dict.fromkeys(
                term
                for term in (clean_query, *method_intent.expanded_terms)
                if len(term.strip()) >= 2
            )
        )
    terms = [clean_query]
    lowered = clean_query.casefold()
    for triggers, expanded in _TOPIC_QUERY_EXPANSIONS:
        if any(trigger.casefold() in lowered for trigger in triggers):
            terms.extend(expanded)
    terms.extend(_candidate_query_tokens(clean_query))
    simplified = re.sub(r"(直线运动|运动|定理|规律|专题|知识点)$", "", clean_query).strip()
    if len(simplified) >= 2:
        terms.append(simplified)
    return list(dict.fromkeys(term for term in terms if len(term.strip()) >= 2))


def _truncate_search_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)].rstrip()}…"


def _search_questions_comprehensive(
    *,
    query: str,
    question_type: str | None,
    difficulty: str | None,
    status: str | None,
    module: str | None,
    topic1_id: str | None,
    topic2_id: str | None,
    topic3_id: str | None,
    topic2: str | None,
    topic3: str | None,
    limit: int,
    offset: int,
    year: int | None = None,
    region: str | None = None,
    exam_type: str | None = None,
    has_media: bool | None = None,
    summary_only: bool = False,
    include_evidence: bool = True,
    confirmed_only: bool = False,
) -> dict[str, Any]:
    """Search canonical, structured, and legacy metadata in one read-only pass."""
    terms = _comprehensive_query_terms(query)
    if not terms:
        return _tool_error("INVALID_ARGUMENT", "query 不能为空。", field="query")

    filters: list[str] = []
    filter_params: list[Any] = []
    for value, clause in (
        (question_type, "q.question_type = ?"),
        (difficulty, "q.difficulty = ?"),
        (status, "q.status = ?"),
        (module, "q.module = ?"),
        (topic2, "q.topic2 = ?"),
        (topic3, "q.topic3 = ?"),
        (1 if has_media is True else (0 if has_media is False else None), "q.has_media = ?"),
    ):
        if value is not None:
            filters.append(clause)
            filter_params.append(value)
    for value in (str(year) if year is not None else None, region, exam_type):
        if value is not None:
            filters.append(
                "(COALESCE(q.source, '') LIKE '%' || ? || '%' "
                "OR COALESCE(qti.source_text, '') LIKE '%' || ? || '%' "
                "OR COALESCE(qs.source_label, '') LIKE '%' || ? || '%')"
            )
            filter_params.extend([value, value, value])
    for value, column in ((topic1_id, "topic1_id"), (topic2_id, "topic2_id"), (topic3_id, "topic3_id")):
        if value is not None:
            filters.append(
                f"EXISTS (SELECT 1 FROM question_knowledge_points qkp_filter "
                f"JOIN knowledge_points kp_filter ON kp_filter.topic3_id = qkp_filter.topic3_id "
                f"WHERE qkp_filter.question_id = q.question_id AND kp_filter.{column} = ?)"
            )
            filter_params.append(value)

    # SQLite's GROUP_CONCAT lets one question retain all of its structured points
    # while the query still sees legacy module/topic/tag values for unbound items.
    where_sql = f" AND {' AND '.join(filters)}" if filters else ""
    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty, q.status,
                   q.module, q.topic2, q.topic3, q.source,
                   qti.title_text, qti.stem_text, qti.answer_text, qti.analysis_text,
                   qti.tags_json, qti.source_text,
                   GROUP_CONCAT(DISTINCT qs.source_label) AS source_labels,
                   GROUP_CONCAT(DISTINCT kp.topic1_name) AS knowledge_topic1_names,
                   GROUP_CONCAT(DISTINCT kp.topic2_name) AS knowledge_topic2_names,
                   GROUP_CONCAT(DISTINCT kp.topic3_name) AS knowledge_topic3_names
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN question_sources qs ON qs.question_id = q.question_id
            LEFT JOIN question_knowledge_points qkp ON qkp.question_id = q.question_id
            LEFT JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id
            WHERE 1 = 1 {where_sql}
            GROUP BY q.question_id
            """,
            filter_params,
        ).fetchall()

    ranked: list[dict[str, Any]] = []
    exact_query = str(query).casefold()
    method_intent = detect_method_intent(query)
    for row in rows:
        candidate = dict(row)
        searchable = {
            "题干": " ".join(str(candidate.get(key) or "") for key in ("canonical_title", "title_text", "stem_text")),
            "解析方法": " ".join(str(candidate.get(key) or "") for key in ("answer_text", "analysis_text")),
            "结构化知识点": " ".join(str(candidate.get(key) or "") for key in ("knowledge_topic1_names", "knowledge_topic2_names", "knowledge_topic3_names")),
            "旧模块/标签": " ".join(str(candidate.get(key) or "") for key in ("module", "topic2", "topic3", "tags_json")),
            "来源": " ".join(str(candidate.get(key) or "") for key in ("source", "source_text", "source_labels")),
        }
        matched_terms: list[str] = []
        matched_sources: list[str] = []
        matched_locations: dict[str, list[str]] = {}
        score = 0
        for term in terms:
            needle = term.casefold()
            fields = [name for name, text in searchable.items() if needle in text.casefold()]
            if not fields:
                continue
            matched_terms.append(term)
            matched_sources.extend(fields)
            matched_locations[term] = fields
            field_score = max(
                110 if term.casefold() == exact_query and name in {"题干", "解析方法", "结构化知识点"} else
                85 if name == "解析方法" else
                80 if name == "题干" else
                70 if name == "结构化知识点" else
                55 if name == "旧模块/标签" else 20
                for name in fields
            )
            score += field_score
        method_match = score_method_candidate(query, candidate, intent=method_intent)
        if method_intent is not None and method_match is None:
            continue
        if method_match is not None:
            score += round(float(method_match["score"]) * 500)
            matched_sources.append("方法结构")
        if not matched_terms and method_match is None:
            continue
        structured_names = str(candidate.get("knowledge_topic3_names") or "").strip()
        metadata_quality = "structured" if structured_names else "legacy_only"
        ranked.append(
            {
                **candidate,
                "search_score": score,
                "matched_terms": matched_terms,
                "matched_sources": list(dict.fromkeys(matched_sources)),
                "matched_locations": matched_locations,
                "metadata_quality": metadata_quality,
                "method_match": method_match,
            }
        )

    ranked.sort(key=lambda item: (-int(item["search_score"]), str(item["question_id"])))
    method_level_counts = {"explicit": 0, "structural": 0, "related": 0}
    for item in ranked:
        method_match = item.get("method_match")
        if isinstance(method_match, dict) and method_match.get("level") in method_level_counts:
            method_level_counts[str(method_match["level"])] += 1
    all_candidate_count = len(ranked)
    if method_intent is not None and confirmed_only:
        ranked = [
            item
            for item in ranked
            if (item.get("method_match") or {}).get("level") in {"explicit", "structural"}
        ]
    total = len(ranked)
    page = ranked[offset : offset + limit]
    page_ids = [str(item["question_id"]) for item in page]
    summaries = {} if summary_only else _fetch_formal_question_summaries(page_ids)
    items: list[dict[str, Any]] = []
    for item in page:
        question_id = str(item["question_id"])
        method_match = dict(item.get("method_match") or {})
        if not include_evidence:
            method_match.pop("evidence", None)
        elif summary_only and method_match.get("evidence"):
            method_match["evidence"] = [
                _truncate_search_text(value, 240)
                for value in method_match["evidence"][:3]
            ]
        if summary_only:
            payload = {
                "question_id": question_id,
                "title": _truncate_search_text(
                    item.get("title_text") or item.get("canonical_title"), 80
                ),
                "source": _truncate_search_text(
                    item.get("source_labels") or item.get("source_text") or item.get("source"),
                    100,
                ),
                "question_type": item.get("question_type"),
                "difficulty": item.get("difficulty"),
                "method_level": method_match.get("level"),
            }
            if include_evidence:
                payload["method_match"] = method_match
                payload["matched_sources"] = item["matched_sources"]
        else:
            payload = dict(summaries.get(question_id) or {})
            if not payload:
                payload = {
                    "question_id": question_id,
                    "title": item.get("title_text") or item.get("canonical_title"),
                    "question_type": item.get("question_type"),
                    "difficulty": item.get("difficulty"),
                    "source": item.get("source_labels") or item.get("source_text") or item.get("source"),
                    "tags": _parse_tags(item.get("tags_json")),
                }
            payload["search_match"] = {
                "score": item["search_score"],
                "matched_terms": item["matched_terms"],
                "matched_sources": item["matched_sources"],
                "metadata_quality": item["metadata_quality"],
            }
            if include_evidence:
                payload["search_match"]["matched_locations"] = item["matched_locations"]
            if method_match:
                payload["method_match"] = method_match
        items.append(payload)

    legacy_only_ids = [str(item["question_id"]) for item in ranked if item["metadata_quality"] == "legacy_only"]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "search_mode": "comprehensive",
        "response_mode": "compact" if summary_only else "full",
        "evidence_included": include_evidence,
        "query": query,
        "expanded_terms": terms,
        "method_search": (
            {
                "method_id": method_intent.method_id,
                "method_name": method_intent.method_name,
                "branches": list(method_intent.branches),
                "classification": ["explicit", "structural", "related"],
                "level_counts": method_level_counts,
                "confirmed_count": method_level_counts["explicit"] + method_level_counts["structural"],
                "related_candidate_count": method_level_counts["related"],
                "all_candidate_count": all_candidate_count,
                "confirmed_only": bool(confirmed_only),
                "scanned_all_filtered_questions": True,
                "instruction": (
                    "先按匹配等级筛选；related 不得计入已确认总数。需要核验原文时，"
                    "以 summary_only=false、include_evidence=true 再调用。"
                    if summary_only and not include_evidence
                    else "回答时按匹配等级分组；related 不得计入已确认总数。"
                ),
            }
            if method_intent is not None
            else None
        ),
        "unbound_legacy_question_ids": legacy_only_ids,
        "next_action": (
            "结果已合并结构化知识点和旧标签；若需要提升后续按知识树检索的完整性，"
            "可用 organize_knowledge_tree 为 unbound_legacy_question_ids 补绑知识点。"
            if legacy_only_ids else "结果均已有结构化知识点绑定。"
        ),
        "database_scope": "canonical_read_only",
    }


def _legacy_search_topic_questions(
    query: str,
    question_type: str | None = None,
    difficulty: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """一站式主题检索：自动合并知识树、旧模块、题型标签和题干命中，并标出待补绑题目。只读。"""
    return _search_questions_comprehensive(
        query=str(query or "").strip(),
        question_type=question_type,
        difficulty=difficulty,
        status=None,
        module=None,
        topic1_id=None,
        topic2_id=None,
        topic3_id=None,
        topic2=None,
        topic3=None,
        limit=min(max(int(limit or 20), 1), 50),
        offset=max(int(offset or 0), 0),
    )


def _search_method_questions_indexed(
    *,
    query: str,
    question_type: str | None,
    difficulty: str | None,
    limit: int,
    offset: int,
    year: int | None,
    region: str | None,
    summary_only: bool,
    include_evidence: bool,
    confirmed_only: bool,
    index_refresh: dict[str, int],
) -> dict[str, Any]:
    intent = detect_method_intent(query)
    if intent is None:
        return _tool_error("UNSUPPORTED_METHOD_QUERY", "未识别解题方法。", field="query")

    filters = ["mf.method_id = ?"]
    params: list[Any] = [intent.method_id]
    branch_placeholders = ",".join("?" for _ in intent.branches)
    filters.append(f"mf.branch IN ({branch_placeholders})")
    params.extend(intent.branches)
    if question_type is not None:
        filters.append("q.question_type = ?")
        params.append(question_type)
    if difficulty is not None:
        filters.append("q.difficulty = ?")
        params.append(difficulty)
    for value in (str(year) if year is not None else None, region):
        if value is None:
            continue
        filters.append(
            "(COALESCE(q.source, '') LIKE '%' || ? || '%' "
            "OR COALESCE(qti.source_text, '') LIKE '%' || ? || '%' "
            "OR COALESCE(qs.source_label, '') LIKE '%' || ? || '%')"
        )
        params.extend([value, value, value])

    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            f"""
            SELECT mf.question_id, mf.method_id, mf.branch, mf.level, mf.score,
                   mf.match_basis, mf.evidence_json,
                   q.canonical_title, q.question_type, q.difficulty, q.status, q.source,
                   qti.title_text, qti.stem_text, qti.answer_text, qti.analysis_text,
                   qti.tags_json, qti.source_text,
                   GROUP_CONCAT(DISTINCT qs.source_label) AS source_labels
            FROM question_method_features mf
            JOIN questions q ON q.question_id = mf.question_id
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN question_sources qs ON qs.question_id = q.question_id
            WHERE {' AND '.join(filters)}
            GROUP BY mf.question_id, mf.branch
            """,
            params,
        ).fetchall()

    level_rank = {"explicit": 3, "structural": 2, "related": 1}
    best_by_question: dict[str, dict[str, Any]] = {}
    for raw in rows:
        item = dict(raw)
        question_id = str(item["question_id"])
        current = best_by_question.get(question_id)
        candidate_key = (
            level_rank.get(str(item.get("level")), 0),
            float(item.get("score") or 0),
        )
        current_key = (
            level_rank.get(str(current.get("level")), 0),
            float(current.get("score") or 0),
        ) if current else (-1, -1.0)
        if current is None or candidate_key > current_key:
            best_by_question[question_id] = item

    ranked = sorted(
        best_by_question.values(),
        key=lambda item: (
            -level_rank.get(str(item.get("level")), 0),
            -float(item.get("score") or 0),
            str(item["question_id"]),
        ),
    )
    level_counts = {"explicit": 0, "structural": 0, "related": 0}
    for item in ranked:
        level = str(item.get("level") or "")
        if level in level_counts:
            level_counts[level] += 1
    all_candidate_count = len(ranked)
    if confirmed_only:
        ranked = [item for item in ranked if item.get("level") in {"explicit", "structural"}]
    total = len(ranked)
    page = ranked[offset : offset + limit]
    summaries = (
        {}
        if summary_only
        else _fetch_formal_question_summaries([str(item["question_id"]) for item in page])
    )
    terms = _comprehensive_query_terms(query)
    items: list[dict[str, Any]] = []
    for item in page:
        question_id = str(item["question_id"])
        try:
            evidence = json.loads(str(item.get("evidence_json") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = []
        method_match = {
            "method_id": str(item["method_id"]),
            "method_name": intent.method_name,
            "branch": str(item["branch"]),
            "level": str(item["level"]),
            "match_basis": str(item["match_basis"]),
            "score": round(float(item["score"]), 4),
        }
        if include_evidence:
            method_match["evidence"] = [
                _truncate_search_text(value, 240) if summary_only else str(value)
                for value in list(evidence)[:3]
            ]

        source = item.get("source_labels") or item.get("source_text") or item.get("source")
        if summary_only:
            payload: dict[str, Any] = {
                "question_id": question_id,
                "title": _truncate_search_text(
                    item.get("title_text") or item.get("canonical_title"), 80
                ),
                "source": _truncate_search_text(source, 100),
                "question_type": item.get("question_type"),
                "difficulty": item.get("difficulty"),
                "method_level": item.get("level"),
            }
            if include_evidence:
                payload["method_match"] = method_match
        else:
            payload = dict(summaries.get(question_id) or {})
            if not payload:
                payload = {
                    "question_id": question_id,
                    "title": item.get("title_text") or item.get("canonical_title"),
                    "question_type": item.get("question_type"),
                    "difficulty": item.get("difficulty"),
                    "source": source,
                    "tags": _parse_tags(item.get("tags_json")),
                }
            searchable = {
                "题干": " ".join(
                    str(item.get(key) or "")
                    for key in ("canonical_title", "title_text", "stem_text")
                ),
                "解析方法": " ".join(
                    str(item.get(key) or "") for key in ("answer_text", "analysis_text")
                ),
                "旧模块/标签": str(item.get("tags_json") or ""),
                "来源": str(source or ""),
            }
            matched_locations = {
                term: [
                    field_name
                    for field_name, text_value in searchable.items()
                    if term.casefold() in text_value.casefold()
                ]
                for term in terms
                if any(term.casefold() in value.casefold() for value in searchable.values())
            }
            payload["search_match"] = {
                "score": round(float(item["score"]) * 500),
                "matched_terms": list(matched_locations),
                "matched_sources": list(
                    dict.fromkeys(
                        source_name
                        for names in matched_locations.values()
                        for source_name in names
                    )
                ),
            }
            if include_evidence:
                payload["search_match"]["matched_locations"] = matched_locations
            payload["method_match"] = method_match
        items.append(payload)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "search_mode": "method_index",
        "response_mode": "compact" if summary_only else "full",
        "evidence_included": include_evidence,
        "query": query,
        "method_search": {
            "method_id": intent.method_id,
            "method_name": intent.method_name,
            "branches": list(intent.branches),
            "classification": ["explicit", "structural", "related"],
            "level_counts": level_counts,
            "confirmed_count": level_counts["explicit"] + level_counts["structural"],
            "related_candidate_count": level_counts["related"],
            "all_candidate_count": all_candidate_count,
            "confirmed_only": confirmed_only,
            "instruction": (
                "先按匹配等级筛选；related 不得计入已确认总数。需要核验原文时，"
                "以 summary_only=false、include_evidence=true 再调用。"
            ),
        },
        "method_index": {
            "index_version": METHOD_INDEX_VERSION,
            "refreshed_question_count": int(index_refresh.get("question_count", 0)),
            "was_current": int(index_refresh.get("missing_count", 0)) == 0,
        },
        "database_scope": "canonical_read_only_with_derived_index",
    }


def _legacy_search_method_questions(
    query: str,
    year: int | None = None,
    region: str | None = None,
    question_type: str | None = None,
    difficulty: str | None = None,
    limit: int = 20,
    offset: int = 0,
    summary_only: bool = True,
    include_evidence: bool = False,
    confirmed_only: bool = True,
) -> dict[str, Any]:
    """按解题方法或教学俗称检索正式题库；默认返回轻量摘要。

    不要求题干写出方法名，会同时扫描题干、解析、公式和物理场景结构。
    结果分为 explicit（明确写出）、structural（结构上使用）和 related（仅相关候选）；
    related 不计入已确认题目数，默认 confirmed_only=true 不返回 related；需要扩展
    候选时再关闭。summary_only=true 时只返回筛选所需字段；需要完整
    题干与逐词命中位置时设为 false，需要方法证据时再开启 include_evidence。
    提供年份、地区时请使用结构化参数。
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return _tool_error("INVALID_ARGUMENT", "query 不能为空。", field="query")
    if detect_method_intent(clean_query) is None:
        return _tool_error(
            "UNSUPPORTED_METHOD_QUERY",
            "当前尚未建立该解题方法的结构规则；可改用 search_questions(comprehensive) 做开放检索。",
            field="query",
            supported_methods=["配速法", "重力配速法", "电场配速法", "漂移速度法"],
        )
    index_refresh = ensure_method_feature_index_current(db_path=_formal_db_path())
    return _search_method_questions_indexed(
        query=clean_query,
        question_type=question_type,
        difficulty=difficulty,
        limit=min(max(int(limit or 20), 1), 50),
        offset=max(int(offset or 0), 0),
        year=year,
        region=region,
        summary_only=bool(summary_only),
        include_evidence=bool(include_evidence),
        confirmed_only=bool(confirmed_only),
        index_refresh=index_refresh,
    )


def _legacy_record_method_retrieval_feedback(
    question_id: str,
    method_query: str,
    verdict: Literal["correct", "incorrect", "missed"],
    branch: Literal["gravity", "electric"] | None = None,
    reason: str | None = None,
    maintain_metadata: bool = True,
    operator: str = "teacher",
) -> dict[str, Any]:
    """记录教师对方法检索的确认、误命中或漏检反馈，并刷新标签、知识点、embedding 与方法索引。

    correct/missed 会成为该分支的高置信度方法证据；incorrect 会永久压制该题在该
    分支中的方法命中。泛称“配速法”同时包含两个分支，必须显式提供 branch。
    """
    intent = detect_method_intent(str(method_query or "").strip())
    if intent is None:
        return _tool_error("UNSUPPORTED_METHOD_QUERY", "尚未建立该方法规则。", field="method_query")
    resolved_branch = branch
    if resolved_branch is None and len(intent.branches) == 1:
        resolved_branch = intent.branches[0]
    if resolved_branch not in intent.branches:
        return _tool_error(
            "INVALID_ARGUMENT",
            "请提供与 method_query 一致的 gravity 或 electric 分支。",
            field="branch",
        )
    try:
        return _record_method_retrieval_feedback(
            question_id=str(question_id or "").strip(),
            method_id=intent.method_id,
            branch=resolved_branch,
            verdict=verdict,
            reason=reason,
            operator=operator,
            maintain_metadata=bool(maintain_metadata),
            db_path=_formal_db_path(),
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))


def _legacy_list_method_retrieval_feedback(
    question_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """列出方法检索教师反馈及其审计信息。只读。"""
    try:
        items = _list_method_retrieval_feedback(
            question_id=str(question_id or "").strip() or None,
            limit=min(max(int(limit or 100), 1), 500),
            db_path=_formal_db_path(),
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))
    return {"items": items, "total": len(items), "database_scope": "canonical_feedback_audit"}


def _legacy_method_retrieval_learning_report(limit: int = 50) -> dict[str, Any]:
    """汇总方法检索的长期学习状态：教师反馈、回归约束和待维护元数据。只读。"""
    try:
        return _build_method_retrieval_learning_report(
            limit=min(max(int(limit or 50), 1), 200),
            db_path=_formal_db_path(),
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))


def _legacy_get_questions_by_ids(question_ids: list[str]) -> dict[str, Any]:
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


def _legacy_export_questions_to_typst(
    question_ids: list[str],
    title: str | None = None,
    include_answers: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """将正式题库导出为供任意 Typst 模板 import 的题目数据；默认只预览且不修改图库。"""
    try:
        return _typst_export_service().export(
            question_ids,
            title=title,
            include_answers=include_answers,
            dry_run=dry_run,
        )
    except TypstExportError as exc:
        return _tool_error("INVALID_ARGUMENT", str(exc), field="question_ids")


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
    result = _dump_model(draft)
    result["document_kind"] = "workbench_draft"
    return result, None


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


def _compose_lock_error(draft: dict[str, Any]) -> dict[str, Any] | None:
    lock = (draft.get("metadata") or {}).get("composition_lock")
    if not isinstance(lock, dict) or not lock.get("locked"):
        return None
    return _tool_error(
        "DRAFT_LOCKED",
        "组卷工作台已锁定，请先调用 lock_composition_workbench(locked=false) 再修改。",
        draft_id=draft.get("id"),
        lock=lock,
    )


def _knowledge_content_fields(raw: dict[str, Any]) -> tuple[str, str, list[str]]:
    content = str(raw.get("content") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        summary = content
    raw_points = raw.get("points") or []
    points = [str(point).strip() for point in raw_points if str(point).strip()]
    if not points and content:
        candidates = []
        for line in content.splitlines():
            clean = re.sub(r"^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[.)]\s+)", "", line).strip()
            if clean:
                candidates.append(clean)
        points = candidates[:12] or [content]
    return content, summary, points


def _snapshot_compose_draft(draft: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(draft.get("metadata") or {})
    snapshots = list(metadata.get("snapshots") or [])
    snapshots.append(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "item_count": len(draft.get("items") or []),
            "items": draft.get("items") or [],
        }
    )
    metadata["snapshots"] = snapshots[-10:]
    return {**draft, "metadata": metadata}


def _save_compose_draft(draft: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    request = PaperDraftUpsertRequest(
        id=draft["id"],
        base_updated_at=draft.get("updated_at"),
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


def _legacy_list_composition_workbenches(limit: int = 20) -> dict[str, Any]:
    """列出已保存的组卷工作台草稿。只读；草稿不会修改正式题库。"""
    result = _paper_draft_service().list(limit=min(max(int(limit or 20), 1), 100))
    return {"ok": True, "items": _dump_model(result).get("items", []), "database_scope": "composition_workspace"}


def _legacy_get_composition_workbench(draft_id: str | None = None) -> dict[str, Any]:
    """读取一份组卷工作台草稿；不传 draft_id 时读取最近编辑的一份。只读。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    return {"ok": True, "database_scope": "composition_workspace", "draft": draft}


def _legacy_create_composition_workbench(
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


def _legacy_add_questions_to_composition_workbench(
    question_ids: list[str],
    draft_id: str | None = None,
    insert_at: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把正式题库中的题号引用加入组卷工作台。仅写草稿，不会修改题库题目。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
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


def _legacy_add_knowledge_to_composition_workbench(
    topic3_ids: list[str],
    draft_id: str | None = None,
    insert_at: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """把标准三级知识点作为目录引用加入工作台，不生成教学讲解。仅写草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
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
        display_title = str(topic["topic3_name"])
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
                    "summary": "",
                    "points": [],
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


def _legacy_insert_teaching_block_to_composition_workbench(
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
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
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


def _legacy_reorder_composition_workbench(
    ordered_item_ids: list[str] | None = None,
    draft_id: str | None = None,
    dry_run: bool = False,
    item_id: str | None = None,
    after_item_id: str | None = None,
) -> dict[str, Any]:
    """按完整列表或单项定位调整组卷工作台顺序。仅写草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
    items = list(draft.get("items") or [])
    current_ids = [str(item.get("id") or "") for item in items]
    if item_id:
        requested_ids = _move_composition_ids(current_ids, item_id, after_item_id)
        if requested_ids is None:
            return {"ok": False, "error": "item_id 或 after_item_id 不存在于当前草稿。", "current_item_ids": current_ids}
    else:
        requested_ids = [str(item).strip() for item in (ordered_item_ids or []) if str(item).strip()]
    if len(requested_ids) != len(items) or set(requested_ids) != set(current_ids):
        return {
            "ok": False,
            "error": "ordered_item_ids 必须包含当前草稿中的每一个 item id 各一次；单项调整请使用 item_id + after_item_id。",
            "current_item_ids": current_ids,
        }
    item_map = {str(item["id"]): item for item in items}
    next_items = [item_map[item_id] for item_id in requested_ids]
    if dry_run:
        return _compose_draft_preview(draft, next_items, action="reorder_items")
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "reorder_items", "draft": saved}


def _move_composition_ids(current_ids: list[str], item_id: str, after_item_id: str | None) -> list[str] | None:
    clean_item_id = str(item_id or "").strip()
    clean_after_id = str(after_item_id or "").strip()
    if clean_item_id not in current_ids or (clean_after_id and clean_after_id not in current_ids):
        return None
    if clean_after_id == clean_item_id:
        return current_ids[:]
    result = [value for value in current_ids if value != clean_item_id]
    if not clean_after_id:
        result.insert(0, clean_item_id)
        return result
    result.insert(result.index(clean_after_id) + 1, clean_item_id)
    return result


def _legacy_move_composition_item(
    item_id: str,
    after_item_id: str | None = None,
    draft_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """移动一个工作台对象；after_item_id 为空时移动到最前。"""
    return reorder_composition_workbench(
        draft_id=draft_id,
        dry_run=dry_run,
        item_id=item_id,
        after_item_id=after_item_id,
    )


def _legacy_remove_items_from_composition_workbench(
    item_ids: list[str],
    draft_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """删除指定工作台对象，不影响正式题库。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
    requested = list(dict.fromkeys(str(item_id).strip() for item_id in item_ids if str(item_id).strip()))
    current = list(draft.get("items") or [])
    current_ids = {str(item.get("id") or "") for item in current}
    missing = [item_id for item_id in requested if item_id not in current_ids]
    removed = [item_id for item_id in requested if item_id in current_ids]
    next_items = [item for item in current if str(item.get("id") or "") not in set(removed)]
    if dry_run:
        preview = _compose_draft_preview(draft, next_items, action="remove_items")
        preview.update({"removed_item_ids": removed, "missing_item_ids": missing})
        return preview
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "remove_items", "draft": saved, "removed_item_ids": removed, "missing_item_ids": missing}


def _legacy_update_composition_item(
    item_id: str,
    payload: dict[str, Any],
    draft_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """就地编辑工作台对象的标题和 payload。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
    if not isinstance(payload, dict):
        return _tool_error("INVALID_ARGUMENT", "payload 必须是对象。", field="payload")
    items = list(draft.get("items") or [])
    target = next((item for item in items if str(item.get("id") or "") == str(item_id).strip()), None)
    if target is None:
        return _tool_error("ITEM_NOT_FOUND", "工作台对象不存在。", field="item_id", item_id=item_id)
    if "type" in payload and str(payload["type"]) != str(target.get("type")):
        return _tool_error("INVALID_ARGUMENT", "不能通过 update_composition_item 修改对象类型。", field="payload.type")
    updated = dict(target)
    target_payload = dict(target.get("payload") or {})
    clean_payload = {key: value for key, value in payload.items() if key != "type"}
    if "title" in clean_payload:
        updated["title"] = str(clean_payload.pop("title") or "").strip() or target.get("title")
    if target.get("type") == "knowledge":
        knowledge_payload = {**target_payload, **clean_payload}
        if "content" in clean_payload and "points" not in clean_payload:
            knowledge_payload["points"] = []
        content, summary, points = _knowledge_content_fields(knowledge_payload)
        clean_payload.update({"content": content, "summary": summary, "points": points})
        if "related_question_ids" in clean_payload:
            clean_payload["relatedQuestionIds"] = clean_payload.pop("related_question_ids")
    target_payload.update(clean_payload)
    updated["payload"] = target_payload
    next_items = [updated if item is target else item for item in items]
    if dry_run:
        return _compose_draft_preview(draft, next_items, action="update_item")
    saved = _save_compose_draft(draft, next_items)
    return {"ok": True, "dry_run": False, "action": "update_item", "draft": saved, "updated_item_id": item_id}


def _legacy_lock_composition_workbench(
    locked: bool = True,
    draft_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """锁定或解锁工作台，防止自动保存或并发操作替换内容。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    metadata = dict(draft.get("metadata") or {})
    metadata["composition_lock"] = {
        "locked": bool(locked),
        "reason": str(reason or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    request = PaperDraftUpsertRequest(
        id=draft["id"],
        base_updated_at=draft.get("updated_at"),
        title=draft["title"],
        subtitle=draft.get("subtitle"),
        source=draft.get("source") or "ai",
        status=draft.get("status") or "draft",
        items=[PaperDraftItem(**{**item, "position": index}) for index, item in enumerate(draft.get("items") or [])],
        metadata=metadata,
        quality_report=draft.get("quality_report") or {},
    )
    saved = _dump_model(_paper_draft_service().save(request))
    return {"ok": True, "action": "lock_composition_workbench", "locked": bool(locked), "draft": saved}


def _legacy_apply_composition_workbench_plan(
    operations: list[dict[str, Any]],
    draft_id: str | None = None,
    ordered_refs: list[str] | None = None,
    mode: Literal["full", "patch"] = "patch",
    dry_run: bool = False,
) -> dict[str, Any]:
    """一次完成组卷计划：批量加入题目、完整知识讲解卡或教学文字并排序。

    knowledge 可引用准确的 topic3_id，也可仅提供 title；必须提供非空 summary/content
    或 points，内容会直接成为工作台可见、可编辑的讲解。请围绕关联题目的实际判断过程
    自然组织内容，不要套用固定栏目。没有准确目录节点时不要绑定近似节点。
    ordered_refs 可用 item:<现有item_id> 与 operation.ref 指定最终顺序。仅写组卷草稿。
    """
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    lock_error = _compose_lock_error(draft)
    if lock_error:
        return lock_error
    if mode not in {"full", "patch"}:
        return _tool_error("INVALID_ARGUMENT", "mode 仅支持 full 或 patch。", field="mode")
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
            title = str(raw.get("title") or "").strip()
            if not topic3_id and not title:
                return {"ok": False, "error": f"{ref} 的 knowledge 至少需要准确的 topic3_id 或 title。"}
            raw_points = raw.get("points") or []
            if not isinstance(raw_points, list):
                return {"ok": False, "error": f"{ref} 的 points 必须是字符串数组。"}
            if "content" in raw and raw.get("content") is not None and not isinstance(raw.get("content"), str):
                return {"ok": False, "error": f"{ref} 的 content 必须是 Markdown 字符串。"}
            related_question_ids = raw.get("related_question_ids") or []
            if not isinstance(related_question_ids, list):
                return {"ok": False, "error": f"{ref} 的 related_question_ids 必须是题号数组。"}
            if topic3_id:
                topic_requests.append(topic3_id)
            content, summary, points = _knowledge_content_fields(raw)
            if not summary and not points:
                return {
                    "ok": False,
                    "error": f"{ref} 缺少实际讲解内容。请根据关联题目填写 content/summary 或 points，不能只传知识点编号。",
                }
            normalized_ops.append({
                "ref": ref,
                "kind": kind,
                "topic3_id": topic3_id,
                "title": title,
                "content": content,
                "summary": summary,
                "points": points,
                "related_question_ids": [
                    str(question_id).strip()
                    for question_id in related_question_ids
                    if str(question_id).strip()
                ],
            })
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
    existing_topic_refs = {
        str((item.get("payload") or {}).get("topic3_id") or (item.get("payload") or {}).get("id") or ""): f"item:{item['id']}"
        for item in existing_items
        if item.get("type") == "knowledge"
        and str((item.get("payload") or {}).get("topic3_id") or (item.get("payload") or {}).get("id") or "")
    }
    produced: dict[str, dict[str, Any]] = {}
    replacement_refs: dict[str, str] = {}
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
            if topic3_id and topic3_id not in topics:
                return {"ok": False, "error": f"标准知识目录不存在 active topic3_id：{topic3_id}。"}
            topic = _topic_payload(topics[topic3_id]) if topic3_id else {}
            default_title = str(topic["topic3_name"]) if topic else "知识讲解"
            title = operation["title"] or default_title
            knowledge_id = topic3_id or f"ai-knowledge-{_short_id()}"
            replaced_ref = existing_topic_refs.pop(topic3_id, None) if topic3_id else None
            replaced_item = existing_refs.pop(replaced_ref, None) if replaced_ref else None
            if replaced_ref:
                replacement_refs[replaced_ref] = ref
            produced[ref] = {
                "id": str((replaced_item or {}).get("id") or f"compose-knowledge-{_short_id()}"),
                "type": "knowledge",
                "position": 0,
                "title": title,
                "payload": {
                    "id": knowledge_id,
                    "topic3_id": topic3_id or None,
                    "title": title,
                    "content": operation["content"],
                    "summary": operation["summary"],
                    "points": operation["points"],
                    "relatedQuestionIds": operation["related_question_ids"],
                    **topic,
                },
            }
        else:
            produced[ref] = {"id": f"compose-text-{_short_id()}", "type": "text", "position": 0, "title": operation["title"], "payload": {"id": f"text-{_short_id()}", "title": operation["title"], "content": operation["content"], "blockKind": operation["block_kind"]}}

    all_refs = {**existing_refs, **produced}
    default_order = [
        replacement_refs.get(f"item:{item['id']}", f"item:{item['id']}")
        for item in existing_items
    ]
    default_order.extend(ref for ref in produced if ref not in default_order)
    requested_order = [
        replacement_refs.get(str(ref).strip(), str(ref).strip())
        for ref in (ordered_refs or default_order)
        if str(ref).strip()
    ]
    if len(requested_order) != len(set(requested_order)) or any(ref not in all_refs for ref in requested_order):
        return {"ok": False, "error": "ordered_refs 包含重复或不存在的引用。", "available_refs": list(all_refs), "skipped": skipped}
    if mode == "full" and (len(requested_order) != len(all_refs) or set(requested_order) != set(all_refs)):
        return {"ok": False, "error": "mode=full 时 ordered_refs 必须包含每个保留对象和新增对象各一次。", "available_refs": list(all_refs), "skipped": skipped}
    if mode == "patch":
        requested_order.extend(ref for ref in default_order if ref not in requested_order)
        requested_order.extend(ref for ref in all_refs if ref not in requested_order)
    next_items = [all_refs[ref] for ref in requested_order]
    if dry_run:
        preview = _compose_draft_preview(draft, next_items, action="apply_composition_plan")
        preview.update({"available_refs": {ref: item["id"] for ref, item in all_refs.items()}, "skipped": skipped})
        return preview
    try:
        saved = _save_compose_draft(_snapshot_compose_draft(draft), next_items)
    except PaperDraftConflictError:
        return _tool_error(
            "DRAFT_CONFLICT",
            "组卷工作台刚被其他操作更新，本次未覆盖新内容。请重新读取工作台后再执行计划。",
            retryable=True,
            draft_id=draft["id"],
            next_tools=["get_composition_workbench", "apply_composition_workbench_plan"],
        )
    return {"ok": True, "dry_run": False, "action": "apply_composition_plan", "draft": saved, "skipped": skipped}


def _composition_preview_markdown(draft: dict[str, Any]) -> str:
    lines = [f"# {draft.get('title') or 'Untitled lesson'}"]
    if draft.get("subtitle"):
        lines.extend(["", str(draft["subtitle"])])
    for index, item in enumerate(draft.get("items") or [], start=1):
        item_type = str(item.get("type") or "item")
        title = str(item.get("title") or (item.get("payload") or {}).get("title") or item_type)
        lines.extend(["", f"## {index}. {title}"])
        payload = item.get("payload") or {}
        if item_type == "question":
            lines.append(str(payload.get("stem") or payload.get("title") or item.get("question_id") or ""))
        elif item_type == "knowledge":
            lines.append(str(payload.get("content") or payload.get("summary") or ""))
            lines.extend(f"- {point}" for point in payload.get("points") or [])
        elif item_type == "text":
            lines.append(str(payload.get("content") or ""))
        else:
            lines.append("---")
    return "\n".join(lines).strip() + "\n"


def _legacy_preview_composition_workbench(
    draft_id: str | None = None,
    format: Literal["markdown", "html"] = "markdown",
) -> dict[str, Any]:
    """返回工作台的可读 Markdown 或 HTML 预览，不修改草稿。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    if format not in {"markdown", "html"}:
        return _tool_error("INVALID_ARGUMENT", "format 仅支持 markdown 或 html。", field="format")
    markdown = _composition_preview_markdown(draft)
    content = markdown
    if format == "html":
        blocks = "<br>\n".join(html.escape(line) for line in markdown.splitlines())
        content = f'<article class="composition-workbench-preview">{blocks}</article>'
    return {"ok": True, "draft_id": draft["id"], "format": format, "content": content}


def _composition_draft_to_lesson_package(draft: dict[str, Any]) -> dict[str, Any]:
    question_ids = [
        str(item.get("question_id") or "").strip()
        for item in draft.get("items") or []
        if item.get("type") == "question" and str(item.get("question_id") or "").strip()
    ]
    questions = _dump_model(_search_service().get_by_ids(BatchQuestionFetchRequest(question_ids=question_ids))) if question_ids else []
    knowledge_cards: dict[str, dict[str, Any]] = {}
    text_blocks: dict[str, dict[str, Any]] = {}
    nodes: list[dict[str, Any]] = []
    for item in draft.get("items") or []:
        item_type = str(item.get("type") or "")
        payload = dict(item.get("payload") or {})
        item_id = str(item.get("id") or "")
        if item_type == "question":
            nodes.append({"type": "question", "id": item_id, "questionId": item.get("question_id")})
        elif item_type == "knowledge":
            knowledge_id = str(payload.get("topic3_id") or payload.get("id") or item_id)
            knowledge_cards[knowledge_id] = {"id": knowledge_id, **payload, "title": payload.get("title") or item.get("title") or "Knowledge"}
            nodes.append({"type": "knowledge", "id": item_id, "knowledgeId": knowledge_id})
        elif item_type == "text":
            text_id = str(payload.get("id") or item_id)
            text_blocks[text_id] = {"id": text_id, **payload, "title": payload.get("title") or item.get("title") or "Text"}
            nodes.append({"type": "text", "id": item_id, "textBlockId": text_id})
        else:
            nodes.append({"type": "page_break", "id": item_id, "title": item.get("title")})
    return {
        "id": draft["id"],
        "document_kind": "workbench_draft",
        "title": draft.get("title") or "Untitled lesson",
        "subtitle": draft.get("subtitle") or "",
        "source": draft.get("source") or "compose",
        "questions": questions,
        "knowledgeCards": list(knowledge_cards.values()),
        "textBlocks": list(text_blocks.values()),
        "nodes": nodes,
        "styleConfig": (draft.get("metadata") or {}).get("styleConfig") or {},
        "headerFooter": (draft.get("metadata") or {}).get("headerFooter") or {},
        "formatSpec": (draft.get("metadata") or {}).get("formatSpec") or {},
    }


def _legacy_export_composition_workbench(
    draft_id: str | None = None,
    format: Literal["word", "pptx"] = "word",
    include_answers: bool | None = None,
    include_analysis: bool | None = None,
    file_name: str | None = None,
    template_id: str | None = None,
    format_spec: dict[str, Any] | None = None,
    answer_position: Literal["after_question", "end"] | None = None,
) -> dict[str, Any]:
    """把工作台转换为现有导出任务并返回下载任务信息。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    if format not in {"word", "pptx"}:
        return _tool_error("INVALID_ARGUMENT", "format 仅支持 word 或 pptx。", field="format")
    try:
        package = _composition_draft_to_lesson_package(draft)
        package["formatSpec"] = format_spec_for_template(
            template_id,
            format_spec if format_spec is not None else (None if template_id else package.get("formatSpec") or None),
        )
        return _submit_export_job(
            format,
            package,
            include_answers=include_answers,
            include_analysis=include_analysis,
            file_name=file_name,
            answer_position=answer_position,
            context=_task_action_context("composition_workbench", draft["id"], "MCP user"),
        )
    except Exception as exc:  # noqa: BLE001
        return _tool_error("EXPORT_FAILED", str(exc), retryable=False, draft_id=draft["id"])


def _legacy_list_word_export_templates() -> dict[str, Any]:
    """列出可复用的 Word 排版模板；只读。"""
    return {"ok": True, "items": _list_word_export_templates_store(), "schema": "physics-vault/word-export-format/v1"}


def _legacy_get_word_export_template(template_id: str) -> dict[str, Any]:
    """读取一个 Word 排版模板；只读。"""
    # The local tool name shadows the imported service function; resolve by id from the list instead.
    template = next((item for item in _list_word_export_templates_store() if item.get("id") == str(template_id or "").strip()), None)
    if not template:
        return _tool_error("TEMPLATE_NOT_FOUND", f"Word 排版模板不存在：{template_id}。", field="template_id")
    return {"ok": True, "template": template}


def _legacy_propose_word_export_format(
    purpose: Literal["formal_exam", "student_practice", "teacher_handout", "custom"] = "formal_exam",
    requirements: str | None = None,
) -> dict[str, Any]:
    """根据用途返回结构化 Word 排版方案，供智能体预览、修改和保存。"""
    template_id = None if purpose == "custom" else purpose
    if template_id:
        template = next((item for item in _list_word_export_templates_store() if item.get("id") == template_id), None)
        if not template:
            return _tool_error("TEMPLATE_NOT_FOUND", f"内置 Word 排版模板不存在：{template_id}。")
        spec = template.get("formatSpec") or {}
        name = template.get("name")
    else:
        spec = format_spec_for_template(None)
        name = "自定义 Word 排版"
    return {
        "ok": True,
        "purpose": purpose,
        "template_id": template_id,
        "formatSpec": spec,
        "requirements": requirements or "",
        "assumptions": ["未指定的内容沿用模板默认值。", "图片使用题目中的可访问资源路径。", "答案和解析是否导出由 output 配置决定。"],
        "name": name,
    }


def _legacy_validate_word_export_format(format_spec: dict[str, Any]) -> dict[str, Any]:
    """校验 Word 排版规格并返回规范化结果；不修改模板或文档。"""
    return validate_format_spec(format_spec)


def _legacy_save_word_export_template(
    name: str,
    format_spec: dict[str, Any],
    template_id: str | None = None,
    description: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """保存或更新一个可复用的 Word 排版模板。"""
    return _save_word_export_template_store(name, format_spec, template_id=template_id, description=description, overwrite=overwrite)


def _legacy_rename_word_export_template(template_id: str, name: str) -> dict[str, Any]:
    """重命名用户自定义 Word 排版模板；内置模板不可改名。"""
    return _rename_word_export_template_store(template_id, name)


def _legacy_list_saved_handouts(limit: int = 100) -> dict[str, Any]:
    """列出已保存讲义；不会返回工作台草稿。"""
    return {"ok": True, "document_kind": "saved_handout", "items": _list_saved_handouts_store(limit)}


def _legacy_get_saved_handout(document_id: str) -> dict[str, Any]:
    """读取一份已保存讲义的完整内容；不会读取工作台草稿。"""
    document = _get_saved_handout_store(document_id)
    if not document:
        return _tool_error("SAVED_HANDOUT_NOT_FOUND", f"已保存讲义不存在：{document_id}。", field="document_id", next_tools=["list_saved_handouts"])
    return {"ok": True, **document, "document_kind": "saved_handout"}


def _legacy_list_saved_handout_versions(document_id: str) -> dict[str, Any]:
    """列出已保存讲义的版本摘要；不会返回工作台草稿版本。"""
    versions = _list_saved_handout_versions_store(document_id)
    if versions is None:
        return _tool_error("SAVED_HANDOUT_NOT_FOUND", f"已保存讲义不存在：{document_id}。", field="document_id")
    return {"ok": True, "document_kind": "saved_handout", "document_id": document_id, "items": versions}


def _legacy_restore_saved_handout_version(
    document_id: str,
    version: int,
    confirmed: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """恢复已保存讲义的指定版本；必须使用预览返回的 plan_token。"""
    versions = _list_saved_handout_versions_store(document_id)
    if versions is None:
        return _tool_error("SAVED_HANDOUT_NOT_FOUND", f"已保存讲义不存在：{document_id}。", field="document_id")
    selected = next((item for item in versions if int(item.get("version") or 0) == int(version)), None)
    if selected is None:
        return _tool_error("VERSION_NOT_FOUND", f"讲义版本不存在：{version}。", field="version", available_versions=versions)
    def version_snapshot() -> dict[str, Any]:
        latest = _get_saved_handout_store(document_id) or {}
        return {
            "document_id": document_id,
            "current_version": latest.get("currentVersion"),
            "updated_at": latest.get("updatedAt"),
            "restore_version": int(version),
        }
    if not confirmed:
        operation_plan = _persisted_operation_plan_payload(
            action="saved_handout.restore_version",
            targets=[{"type": "saved_handout", "id": document_id, "label": f"restore version {version}"}],
            summary=f"把已保存讲义 {document_id} 恢复为版本 {version}，并生成新的当前版本。",
            warnings=["不会删除历史版本；预览后当前版本发生变化时必须重新预览。"],
            version_snapshot=version_snapshot(),
            reversible=True,
        )
        return {
            "ok": True,
            "dry_run": True,
            "confirmation_required": True,
            "document_kind": "saved_handout",
            "document_id": document_id,
            "version": version,
            "operation_plan": operation_plan,
            "plan_token": operation_plan["operation_id"],
            "message": "恢复不会删除历史版本，但会把当前内容替换为指定版本并生成新版本；请确认后再次以 confirmed=true 调用。",
        }

    def execute_restore() -> dict[str, Any]:
        try:
            restored = _restore_saved_handout_version_store(document_id, version)
        except ValueError as exc:
            return _tool_error("VERSION_NOT_FOUND", str(exc), field="version")
        return {"ok": True, "dry_run": False, "document_kind": "saved_handout", "restored_from_version": version, "document": restored}

    return _execute_persisted_operation(
        plan_token,
        action="saved_handout.restore_version",
        version_snapshot_reader=version_snapshot,
        executor=execute_restore,
    )


def _legacy_rename_saved_handout(document_id: str, title: str) -> dict[str, Any]:
    """重命名已保存讲义；不会修改工作台草稿。"""
    try:
        document = _rename_saved_handout_store(document_id, title)
    except ValueError as exc:
        return _tool_error("INVALID_ARGUMENT", str(exc), field="title")
    if not document:
        return _tool_error("SAVED_HANDOUT_NOT_FOUND", f"已保存讲义不存在：{document_id}。", field="document_id")
    return {"ok": True, **document, "document_kind": "saved_handout"}


def _legacy_apply_word_format_to_saved_handout(
    document_id: str,
    template_id: str | None = None,
    format_spec: dict[str, Any] | None = None,
    dry_run: bool = True,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """把 Word 排版规格应用到已保存讲义；默认预览，执行需 plan_token。"""
    document = _get_saved_handout_store(document_id)
    if not document:
        return _tool_error("SAVED_HANDOUT_NOT_FOUND", f"已保存讲义不存在：{document_id}。", field="document_id")
    package = document.get("lessonPackage") if isinstance(document.get("lessonPackage"), dict) else {}
    current_spec = package.get("formatSpec") if isinstance(package.get("formatSpec"), dict) else None
    before_spec = current_spec or {}
    before_template_id = document.get("formatTemplateId")
    spec = format_spec_for_template(template_id, format_spec if format_spec is not None else (None if template_id else current_spec))
    checked = validate_format_spec(spec)
    if not checked["ok"]:
        return checked
    changes = _format_spec_diff(
        before_spec,
        checked["formatSpec"],
        before_template_id=before_template_id,
        after_template_id=template_id,
    )
    def version_snapshot() -> dict[str, Any]:
        latest = _get_saved_handout_store(document_id) or {}
        return {
            "document_id": document_id,
            "current_version": latest.get("currentVersion"),
            "updated_at": latest.get("updatedAt"),
            "target_template_id": template_id,
            "target_format_spec": checked["formatSpec"],
        }
    if dry_run:
        operation_plan = _persisted_operation_plan_payload(
            action="saved_handout.apply_word_format",
            targets=[{"type": "saved_handout", "id": document_id, "label": str(document.get("title") or document_id)}],
            summary=f"把新的 Word 排版规格应用到已保存讲义 {document_id}。",
            warnings=["应用会生成新的讲义版本；预览后讲义发生变化时必须重新预览。"],
            version_snapshot=version_snapshot(),
            reversible=True,
        )
        return {
            "ok": True,
            "dry_run": True,
            "document_kind": "saved_handout",
            "document_id": document_id,
            "formatSpec": checked["formatSpec"],
            "changes": changes,
            "operation_plan": operation_plan,
            "plan_token": operation_plan["operation_id"],
        }

    def execute_format() -> dict[str, Any]:
        updated = _update_saved_handout_format_store(document_id, checked["formatSpec"], template_id=template_id)
        return {
            "ok": True,
            "dry_run": False,
            "document_kind": "saved_handout",
            "document": updated,
            "formatSpec": checked["formatSpec"],
            "changes": changes,
        }

    return _execute_persisted_operation(
        plan_token,
        action="saved_handout.apply_word_format",
        version_snapshot_reader=version_snapshot,
        executor=execute_format,
    )


def _legacy_apply_word_format_to_workbench(
    draft_id: str | None = None,
    template_id: str | None = None,
    format_spec: dict[str, Any] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """把 Word 排版规格应用到工作台草稿；默认仅预览，执行后仍属于 workbench_draft。"""
    draft, error = _get_compose_draft_or_error(draft_id)
    if error:
        return error
    metadata = dict(draft.get("metadata") or {})
    current_spec = metadata.get("formatSpec") if isinstance(metadata.get("formatSpec"), dict) else None
    before_spec = current_spec or {}
    before_template_id = metadata.get("formatTemplateId")
    spec = format_spec_for_template(template_id, format_spec if format_spec is not None else (None if template_id else current_spec))
    checked = validate_format_spec(spec)
    if not checked["ok"]:
        return checked
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "document_kind": "workbench_draft",
            "draft_id": draft["id"],
            "formatSpec": checked["formatSpec"],
            "changes": _format_spec_diff(
                before_spec,
                checked["formatSpec"],
                before_template_id=before_template_id,
                after_template_id=template_id,
            ),
        }
    metadata["formatSpec"] = checked["formatSpec"]
    metadata["formatTemplateId"] = template_id
    saved = _save_compose_draft({**draft, "metadata": metadata}, list(draft.get("items") or []))
    return {
        "ok": True,
        "dry_run": False,
        "document_kind": "workbench_draft",
        "draft": saved,
        "formatSpec": checked["formatSpec"],
        "changes": _format_spec_diff(
            before_spec,
            checked["formatSpec"],
            before_template_id=before_template_id,
            after_template_id=template_id,
        ),
    }


def _legacy_export_saved_handout(
    document_id: str,
    format: Literal["word"] = "word",
    include_answers: bool | None = None,
    include_analysis: bool | None = None,
    answer_position: Literal["after_question", "end"] | None = None,
    template_id: str | None = None,
    format_spec: dict[str, Any] | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """导出已保存讲义；只读取 saved_handout，不会把工作台草稿当作导出源。"""
    if format != "word":
        return _tool_error("INVALID_ARGUMENT", "已保存讲义目前仅支持 Word 导出。", field="format")
    document = _get_saved_handout_store(document_id)
    if not document:
        return _tool_error("SAVED_HANDOUT_NOT_FOUND", f"已保存讲义不存在：{document_id}。", field="document_id")
    package = document.get("lessonPackage") if isinstance(document.get("lessonPackage"), dict) else None
    if not isinstance(package, dict):
        return _tool_error("INVALID_DOCUMENT", "已保存讲义缺少 lessonPackage。", field="document_id")
    current_spec = package.get("formatSpec") if isinstance(package.get("formatSpec"), dict) else None
    spec = format_spec_for_template(template_id, format_spec if format_spec is not None else (None if template_id else current_spec))
    checked = validate_format_spec(spec)
    if not checked["ok"]:
        return checked
    package = {**package, "formatSpec": checked["formatSpec"]}
    output = checked["formatSpec"].get("output") or {}
    return _submit_export_job(
        "word",
        package,
        include_answers=bool(output.get("includeAnswers")) if include_answers is None else include_answers,
        include_analysis=bool(output.get("includeAnalysis")) if include_analysis is None else include_analysis,
        answer_position=answer_position or str(output.get("answerPosition") or "after_question"),
        file_name=file_name,
        context=_task_action_context("saved_handout", document_id, "MCP user"),
    )


def _find_composition_candidates(query: str, limit: int = 500) -> list[dict[str, Any]]:
    keyword = str(query or "").strip()
    if not keyword:
        return []
    terms = _comprehensive_query_terms(keyword)
    searchable_columns = [
        "q.question_id", "q.canonical_title", "q.module", "q.topic2", "q.topic3", "q.source", "qti.title_text", "qti.stem_text", "qti.tags_json", "qti.source_text",
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
                   qti.title_text, qti.stem_text, qti.tags_json, qti.source_text,
                   GROUP_CONCAT(DISTINCT kp.topic3_name) AS knowledge_topic3_names
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN question_knowledge_points qkp ON qkp.question_id = q.question_id
            LEFT JOIN knowledge_points kp ON kp.topic3_id = qkp.topic3_id
            WHERE (q.status IS NULL OR q.status NOT IN ('deleted', 'archived', 'archived_duplicate'))
              AND ({where})
            GROUP BY q.question_id
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
    expanded_terms = _comprehensive_query_terms(query)
    while remaining and len(selected) < target_count:
        def score(row: dict[str, Any]) -> tuple[int, str]:
            source = str(row.get("source_text") or row.get("source") or "未标注")
            question_type = str(row.get("question_type") or "未标注")
            difficulty = str(row.get("difficulty") if row.get("difficulty") is not None else "未标注")
            title = str(row.get("title_text") or row.get("canonical_title") or "").casefold()
            stem = str(row.get("stem_text") or "").casefold()
            metadata = " ".join(
                str(row.get(field) or "")
                for field in ("module", "tags_json", "knowledge_topic3_names")
            ).casefold()
            relevance = max(
                (
                    8 if term.casefold() == keyword and term.casefold() in title else
                    6 if term.casefold() in title else
                    5 if term.casefold() in metadata else
                    3 if term.casefold() in stem else 0
                )
                for term in expanded_terms
            )
            return (
                relevance
                + (4 if source not in seen_sources else 0)
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


def _legacy_curate_questions_to_composition_workbench(
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


def _legacy_list_knowledge_tree(keyword: str | None = None, limit: int = 200) -> dict[str, Any]:
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


def _legacy_search_knowledge_points(keyword: str, limit: int = 20) -> dict[str, Any]:
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


def _legacy_get_question_knowledge_points(question_id: str) -> dict[str, Any]:
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


def _legacy_maintain_question_knowledge_points(
    question_ids: list[str],
    auto_fix: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    """诊断并维护正式题目的三级知识点绑定。

    每题采用“1 个主知识点 + 最多 2 个辅助知识点”。诊断只依据题干和解析，
    不让旧标签自证正确；auto_fix=true 时仅自动应用高置信度修复，疑难项保留为
    needs_review。修改只涉及检索元数据，并返回可回滚的 audit_batch_id。
    """
    clean_ids = list(dict.fromkeys(str(item or "").strip() for item in question_ids if str(item or "").strip()))
    if not clean_ids:
        return _tool_error("INVALID_ARGUMENT", "question_ids 至少需要一个题号。", field="question_ids")
    try:
        return _metadata_management_service().maintain_question_knowledge_points(
            clean_ids,
            auto_fix=bool(auto_fix),
            reason=reason,
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))


def _legacy_create_knowledge_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    """直接新增正式知识树节点。知识目录是智能体可自治维护的元数据，不需要审核。"""
    try:
        return _metadata_management_service().create_knowledge_points(points)
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)


def _legacy_organize_knowledge_tree(
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


def _legacy_batch_update_question_metadata(
    updates: list[dict[str, Any]],
    reason: str | None = None,
) -> dict[str, Any]:
    """直接统一标签、知识点、难度、题型、来源和试卷关联；不能修改题目正文或发布状态。"""
    try:
        return _metadata_management_service().batch_update_question_metadata(updates, reason=reason)
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)


def _legacy_create_paper(
    paper_id: str,
    name: str,
    year: int,
    region: str,
    exam_type: str,
) -> dict[str, Any]:
    """在正式库创建试卷记录；同 paper_id 幂等，不覆盖冲突记录。"""
    clean_id = str(paper_id or "").strip()
    clean_name = " ".join(str(name or "").split())
    clean_region = " ".join(str(region or "").split())
    clean_exam_type = " ".join(str(exam_type or "").split())
    if not clean_id:
        return _tool_error("INVALID_ARGUMENT", "paper_id 不能为空。", field="paper_id")
    if not clean_name:
        return _tool_error("INVALID_ARGUMENT", "name 不能为空。", field="name")
    if len(clean_id) > 120 or len(clean_name) > 200:
        return _tool_error("INVALID_ARGUMENT", "paper_id 或 name 超出长度限制。", field="paper_id")
    try:
        clean_year = int(year)
    except (TypeError, ValueError):
        return _tool_error("INVALID_ARGUMENT", "year 必须是有效年份。", field="year")
    if clean_year < 1900 or clean_year > 2100:
        return _tool_error("INVALID_ARGUMENT", "year 必须在 1900 到 2100 之间。", field="year")
    if not clean_region or not clean_exam_type:
        return _tool_error("INVALID_ARGUMENT", "region 和 exam_type 不能为空。", field="region")
    try:
        with _connect_formal_write_db() as conn:
            existing = conn.execute(
                "SELECT paper_id, paper_name, year, region, exam_type, subject, status FROM papers WHERE paper_id = ?",
                (clean_id,),
            ).fetchone()
            requested = {
                "paper_id": clean_id,
                "paper_name": clean_name,
                "year": clean_year,
                "region": clean_region,
                "exam_type": clean_exam_type,
            }
            if existing is not None:
                current = dict(existing)
                comparable = {key: current.get(key) for key in requested}
                if comparable != requested:
                    return _tool_error(
                        "PAPER_CONFLICT",
                        f"paper_id 已存在且字段不一致：{clean_id}",
                        paper_id=clean_id,
                        existing=current,
                        requested=requested,
                    )
                return {"ok": True, "created": False, "paper": current}
            conn.execute(
                """
                INSERT INTO papers (paper_id, year, exam_type, region, paper_name, subject, status)
                VALUES (?, ?, ?, ?, ?, 'PHY', 'structured')
                """,
                (clean_id, clean_year, clean_exam_type, clean_region, clean_name),
            )
            conn.commit()
            created = conn.execute(
                "SELECT paper_id, paper_name, year, region, exam_type, subject, status FROM papers WHERE paper_id = ?",
                (clean_id,),
            ).fetchone()
        return {"ok": True, "created": True, "paper": dict(created) if created else requested}
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)


def _legacy_associate_questions_to_paper(
    question_ids: list[str],
    paper_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """将正式题目批量关联到已存在的试卷，不修改题目正文。"""
    normalized_ids = list(dict.fromkeys(str(item).strip() for item in question_ids if str(item).strip()))
    clean_paper_id = str(paper_id or "").strip()
    if not normalized_ids:
        return _tool_error("INVALID_ARGUMENT", "question_ids 至少需要一个有效题号。", field="question_ids")
    if not clean_paper_id:
        return _tool_error("INVALID_ARGUMENT", "paper_id 不能为空。", field="paper_id")
    if len(normalized_ids) > 100:
        return _tool_error("LIMIT_EXCEEDED", "一次最多关联 100 道题。", field="question_ids")
    try:
        return _metadata_management_service().batch_update_question_metadata(
            [{"question_id": question_id, "primary_paper_id": clean_paper_id} for question_id in normalized_ids],
            reason=reason or f"associate questions to paper {clean_paper_id}",
        )
    except (FileNotFoundError, sqlite3.Error) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=True)


def _legacy_database_boundary_report() -> dict[str, Any]:
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
            "review_center_first": ["list_review_tasks", "get_review_task", "get_review_task_full", "validate_review_task", "split_merged_options", "clean_review_task_latex", "update_review_task_draft"],
            "canonical_read_only": ["search_questions", "get_questions_by_ids", "list_knowledge_tree", "search_knowledge_points", "get_question_knowledge_points", "find_similar_questions"],
            "canonical_metadata_write": [
                "create_knowledge_points",
                "batch_update_question_metadata",
                "maintain_question_knowledge_points",
            ],
            "canonical_controlled_content_workflow": ["return_question_to_review", "rollback_change_batch"],
            "rule": "用户说送审、校对中心、草稿、审核任务、那 15 道题时，先走审核库工具；用户明确说正式题库/已入库/组卷找题时，才走正式库检索。",
        },
        "issues": issues,
        "next_tool_when_user_says_submitted_or_review": "list_review_tasks",
    }


def _legacy_get_workflow_guide(intent: str | None = None) -> dict[str, Any]:
    """按用户意图返回推荐 MCP 调用链；只读，不执行任何业务操作。"""
    exposed = _TOOL_REGISTRY.names() if _MCP_PROFILE == "all" else profile_tool_names(_MCP_PROFILE)
    return build_workflow_guide(intent, profile=_MCP_PROFILE, exposed_tools=exposed)


def _study_sheet_template_health() -> dict[str, Any]:
    return study_sheet_template_health(os.getenv("PHYSICS_STUDY_SHEET_ROOT"))


def _embedding_health() -> dict[str, Any]:
    with _connect_formal_read_db() as conn:
        if not _table_exists(conn, "embeddings"):
            return {"status": "table_missing", "ready_questions": 0, "coverage": 0.0}
        active_questions = int(conn.execute(
            "SELECT COUNT(*) FROM questions WHERE COALESCE(status, '') != 'archived_duplicate'"
        ).fetchone()[0])
        ready_questions = int(conn.execute(
            """
            SELECT COUNT(DISTINCT owner_id)
            FROM embeddings
            WHERE owner_type = 'question' AND status = 'ready'
            """
        ).fetchone()[0])
    coverage = ready_questions / active_questions if active_questions else 1.0
    return {
        "status": "ok" if coverage >= 0.98 else "attention",
        "active_questions": active_questions,
        "ready_questions": ready_questions,
        "coverage": round(coverage, 4),
    }


def _legacy_mcp_system_health(include_details: bool = False) -> dict[str, Any]:
    """统一检查工具面、数据库边界、检索向量和学案模板；全程只读。"""
    database = _legacy_database_health_report()
    templates = _study_sheet_template_health()
    embeddings = _embedding_health()
    exposed = _TOOL_REGISTRY.names() if _MCP_PROFILE == "all" else profile_tool_names(_MCP_PROFILE)
    policies = [item for item in tool_policy_manifest() if item["name"] in exposed]

    return build_mcp_system_health(
        profile=_MCP_PROFILE,
        database=database,
        templates=templates,
        embeddings=embeddings,
        policies=policies,
        include_details=include_details,
    )


def _legacy_database_health_report() -> dict[str, Any]:
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


def _legacy_list_review_queue(
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


def _legacy_import_word_folder_to_review(
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


def _legacy_list_review_tasks(
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
            normalized_keyword = _review_search_key(keyword)
            normalized_haystack = _review_search_key(haystack)
            if (
                str(keyword).strip().casefold() not in haystack.casefold()
                and (not normalized_keyword or normalized_keyword not in normalized_haystack)
            ):
                continue
        items.append(item)
        if len(items) >= limit:
            break
    return {"items": items, "total": len(items), "limit": limit, "review_database_path": str(_review_db_path())}


def _legacy_get_review_task(task_id: str, content_limit: int = 20) -> dict[str, Any]:
    """读取审核库中一个校对任务的草稿内容摘要。只读。"""
    tid, row, error = _load_review_task(task_id)
    if error is not None:
        return error
    assert tid is not None and row is not None

    limit = min(max(int(content_limit or 20), 1), 80)
    summary = _parse_json_dict(row["input_summary_json"])
    result = _parse_json_dict(row["result_json"])
    questions = result.get("questions") if isinstance(result.get("questions"), list) else []
    knowledge_drafts = result.get("knowledge_drafts") if isinstance(result.get("knowledge_drafts"), list) else []
    risk_counts: dict[str, int] = {}
    validation = validate_review_task(tid)
    if validation.get("ok"):
        risk_counts = {
            str(item.get("question_id") or ""): int(item.get("risk_count") or 0)
            for item in validation.get("items", [])
            if isinstance(item, dict)
        }
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
        "questions": [
            _review_question_summary(
                item,
                index,
                risk_count=risk_counts.get(
                    str(item.get("question_id") or item.get("id") or item.get("draft_id") or "").strip(),
                ),
            )
            for index, item in enumerate(questions[:limit], start=1)
        ],
        "knowledge_drafts": [
            _review_knowledge_summary(item, index)
            for index, item in enumerate(knowledge_drafts[:limit], start=1)
        ],
        "content_limit": limit,
    }


def _legacy_get_review_task_full(
    task_id: str,
    question_ids: list[str] | None = None,
    include_knowledge: bool = True,
) -> dict[str, Any]:
    """读取审核库中校对任务的完整草稿字段，不截断题干。只读。"""
    tid, row, error = _load_review_task(task_id)
    if error is not None:
        return error
    assert tid is not None and row is not None

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


def _review_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_review_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_review_text(item) for item in value)
    return str(value or "").strip()


def _review_normalized_text(value: Any) -> str:
    # Keep mathematical operators: removing + / - made distinct algebraic
    # options such as "F/3 + μmg" and "F/3 - μmg" look identical.
    return re.sub(r"[\s_，。；、：,.;:!?！？（）()\[\]{}]+", "", _review_text(value), flags=re.UNICODE).casefold()


def _review_search_key(value: Any) -> str:
    """让任务号、批次号搜索忽略空格、短横线和常见 OCR 标点差异。"""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def _review_question_type(item: dict[str, Any]) -> str:
    return str(item.get("question_type") or item.get("type") or "").strip().casefold()


def _review_options(item: dict[str, Any]) -> list[tuple[str, str]]:
    raw = item.get("options") or item.get("choices") or []
    if isinstance(raw, dict):
        raw = [{"label": key, "text": value} for key, value in raw.items()]
    if not isinstance(raw, list):
        return []
    options: list[tuple[str, str]] = []
    for index, option in enumerate(raw):
        if isinstance(option, dict):
            label = str(option.get("label") or option.get("key") or option.get("option") or "").strip()
            text = option.get("text") or option.get("content") or option.get("value") or ""
        else:
            label = ""
            text = option
        label = label.rstrip(".、．") or chr(65 + index)
        options.append((label.upper(), _review_text(text)))
    return options


_REVIEW_FIGURE_PLACEHOLDER_RE = re.compile(r"!\[fig:[^\]]+\]", flags=re.IGNORECASE)


def _review_duplicate_value(value: Any) -> str:
    """Compare question content while ignoring copied image placeholder IDs."""
    without_figure_ids = _REVIEW_FIGURE_PLACEHOLDER_RE.sub("", _review_text(value))
    return re.sub(r"[\s\W_]+", "", without_figure_ids, flags=re.UNICODE).casefold()


def _review_exact_duplicate_signature(item: dict[str, Any]) -> tuple[Any, ...] | None:
    """Return a conservative content signature for safe in-task deduplication."""
    title = _review_duplicate_value(
        item.get("title") or item.get("stem") or item.get("stem_text") or item.get("question_body") or item.get("content")
    )
    answer = _review_duplicate_value(item.get("answer") or item.get("correct_answer"))
    analysis = _review_duplicate_value(item.get("analysis") or item.get("explanation") or item.get("solution"))
    source = _review_duplicate_value(item.get("source") or item.get("origin") or item.get("source_name"))
    options = tuple((label, _review_duplicate_value(text)) for label, text in _review_options(item))
    # An incomplete record is not reliable enough to remove automatically. Short titles are
    # allowed only when the worked analysis independently makes the match specific.
    if (len(title) < 18 and len(analysis) < 40) or not answer or not source:
        return None
    return (_review_question_type(item), title, options, answer, analysis, source)


def _review_figures(item: dict[str, Any]) -> tuple[set[str], list[str]]:
    raw = item.get("figures") or item.get("images") or item.get("question_figures") or []
    if isinstance(raw, dict):
        raw = [raw]
    figure_ids: set[str] = set()
    duplicate_ids: list[str] = []
    if isinstance(raw, list):
        for figure in raw:
            if not isinstance(figure, dict):
                continue
            figure_id = str(
                figure.get("fig_uuid")
                or figure.get("placeholder_key")
                or figure.get("asset_id")
                or figure.get("image_id")
                or figure.get("id")
                or ""
            ).strip()
            if not figure_id:
                continue
            if figure_id in figure_ids:
                duplicate_ids.append(figure_id)
            figure_ids.add(figure_id)
    return figure_ids, duplicate_ids


def _review_risk(code: str, severity: str, field: str, message: str, suggestion: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "field": field,
        "message": message,
        "suggestion": suggestion,
    }


def _is_informational_import_warning(value: Any) -> bool:
    """Keep successful import metadata extraction out of the actionable risk queue."""
    text = _review_text(value)
    return bool(
        re.fullmatch(r"已从(?:答案|题干|原文)中提取(?:难度|知识点|来源)元数据。?", text)
        or re.fullmatch(r"题干具有明确的多步骤实验结构，题型已修正为实验题。?", text)
    )


def _review_workflow_guidance(items: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    """把风险代码转换成下一步可执行的 MCP 工作流提示。"""
    codes = {
        str(risk.get("code") or "")
        for item in items
        if isinstance(item, dict)
        for risk in (item.get("risks") or [])
        if isinstance(risk, dict)
    }
    next_tools: list[str] = []
    actions: list[dict[str, Any]] = []

    if codes & {"missing_options", "too_few_options", "answer_option_mismatch", "duplicate_options", "choice_type_mismatch", "question_type_suspect"}:
        next_tools.append("split_merged_options")
        actions.append({
            "risk_codes": sorted(codes & {"missing_options", "too_few_options", "answer_option_mismatch", "duplicate_options", "choice_type_mismatch", "question_type_suspect"}),
            "tool": "split_merged_options",
            "mode": "dry_run_then_apply",
            "message": "先检查 raw_text 和选项分段；必要时预览拆分合并选项，确认后写回，再重新校验。",
        })
    if codes & {"unbalanced_latex", "malformed_latex"}:
        next_tools.extend(["clean_review_task_latex", "get_review_task_full", "update_review_task_draft"])
        actions.append({
            "risk_codes": sorted(codes & {"unbalanced_latex", "malformed_latex"}),
            "tool": "clean_review_task_latex",
            "mode": "dry_run_then_apply",
            "message": "先预览标准 LaTeX 清洗；写回后必须重新校验。",
        })
        actions.append({
            "risk_codes": sorted(codes & {"unbalanced_latex", "malformed_latex"}),
            "tool": "update_review_task_draft",
            "mode": "manual_standardization",
            "message": "自动清洗后仍有 LaTeX 风险时，先用 get_review_task_full 读取受影响字段，再逐题手动生成并写回标准格式补丁：行内公式用 $...$，独立块公式用 $$...$$，开闭分隔符必须成对且类型一致；写回后重新校验。不要只提示老师手动修改。",
        })
    if codes & {"missing_knowledge"}:
        next_tools.append("organize_knowledge_tree")
        actions.append({
            "risk_codes": ["missing_knowledge"],
            "tool": "organize_knowledge_tree",
            "mode": "apply",
            "message": "让 AI 根据题干和解析匹配或创建知识点，再回读审核草稿确认。",
        })
    if codes & {"missing_source"}:
        next_tools.append("update_review_task_draft")
        actions.append({
            "risk_codes": ["missing_source"],
            "tool": "update_review_task_draft",
            "mode": "dry_run_then_apply",
            "message": "补充试题来源或年份等元数据后重新校验。",
        })
    if codes & {"missing_figure", "unused_figure", "duplicate_figure_id"}:
        next_tools.append("update_review_task_draft")
        actions.append({
            "risk_codes": sorted(codes & {"missing_figure", "unused_figure", "duplicate_figure_id"}),
            "tool": "update_review_task_draft",
            "mode": "dry_run_then_apply",
            "message": "检查图片素材 ID、引用位置和配图关系；必要时更新 figures/题干内容。",
        })
    if codes & {"duplicate_question"}:
        actions.append({
            "risk_codes": ["duplicate_question"],
            "tool": "delete_review_tasks",
            "mode": "manual_confirm",
            "message": "重复题不能自动猜测保留哪一题，需要人工确认后再删除或合并。",
        })

    # 保持工具名去重，同时把完整任务号传给后续调用方。
    next_tools = list(dict.fromkeys(next_tools))
    if not actions and not codes:
        next_tools = ["get_review_task_full"]
    return {
        "task_id": task_id,
        "state": "clean" if not codes else ("needs_manual_review" if codes & {"duplicate_question"} else "needs_cleanup"),
        "next_tools": next_tools,
        "actions": actions,
    }


def _latex_delimiter_status(text: str) -> tuple[bool, bool]:
    """按顺序匹配 $ 与 $$，区分分隔符混用和单纯未闭合。"""
    mode: str | None = None
    malformed = False
    index = 0
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text.startswith("$$", index):
            if mode is None:
                mode = "display"
            elif mode == "display":
                mode = None
            else:
                malformed = True
                mode = None
            index += 2
            continue
        if text[index] == "$":
            if mode is None:
                mode = "inline"
            elif mode == "inline":
                mode = None
            else:
                malformed = True
                mode = None
            index += 1
            continue
        index += 1
    return malformed, mode is not None


def _legacy_validate_review_task(
    task_id: str,
    question_ids: list[str] | None = None,
    require_knowledge: bool = True,
    require_source: bool = True,
    risks_only: bool = False,
) -> dict[str, Any]:
    """检查审核草稿的题型、答案、选项、图片引用、LaTeX 和元数据风险；只读。"""
    # Read the complete draft before writing it back.  ``question_ids`` only
    # narrows the repair target; fetching a filtered subset here would replace
    # the whole task with that subset on save.
    full = get_review_task_full(task_id, include_knowledge=False)
    if not full.get("ok"):
        return full

    questions = full.get("questions") if isinstance(full.get("questions"), list) else []
    items: list[dict[str, Any]] = []
    title_fingerprints: dict[str, list[str]] = {}
    total_counts = {"danger": 0, "warning": 0, "suggestion": 0}

    for index, raw in enumerate(questions, start=1):
        if not isinstance(raw, dict):
            raw = {"content": raw}
        question_id = str(raw.get("question_id") or raw.get("id") or raw.get("draft_id") or f"draft-{index}").strip()
        title = raw.get("title") or raw.get("stem") or raw.get("stem_text") or raw.get("question_body") or raw.get("content")
        options = _review_options(raw)
        question_type = _review_question_type(raw)
        answer = _review_text(raw.get("answer") or raw.get("correct_answer"))
        analysis = _review_text(raw.get("analysis") or raw.get("explanation") or raw.get("solution"))
        knowledge = raw.get("knowledge_points") or raw.get("knowledge_point") or raw.get("topic3_id") or raw.get("topic3_name")
        source = raw.get("source") or raw.get("origin") or raw.get("source_name")
        stem = raw.get("stem") or raw.get("stem_text") or raw.get("question_body") or raw.get("content")
        full_text = _review_text({"title": title, "stem": stem, "options": options, "answer": answer, "analysis": analysis})
        risks: list[dict[str, str]] = []

        if not _review_text(title):
            risks.append(_review_risk("empty_title", "danger", "title", "题干为空。", "补充完整题干后再提交。"))
        fingerprint = _review_normalized_text(title)
        if fingerprint:
            title_fingerprints.setdefault(fingerprint, []).append(question_id)

        choice = any(token in question_type for token in ("choice", "select", "选择", "single", "multiple", "multi"))
        if choice and not options:
            risks.append(_review_risk("missing_options", "danger", "options", "选择题没有识别到选项。", "补充选项或修正题型。"))
        elif choice and len(options) < 2:
            risks.append(_review_risk("too_few_options", "warning", "options", "选择题选项少于 2 个。", "检查图片解析和选项分段。"))
        normalized_options = [_review_normalized_text(text) for _label, text in options if text]
        if len(normalized_options) != len(set(normalized_options)):
            risks.append(_review_risk("duplicate_options", "warning", "options", "存在内容重复的选项。", "检查 OCR 重复或重新分割选项。"))

        if not answer:
            risks.append(_review_risk("missing_answer", "warning", "answer", "未识别到答案。", "补充答案，或明确标记为待确认。"))
        elif choice and options:
            labels = {label.rstrip(".、．") for label, _text in options}
            selected = set(re.findall(r"(?<![A-Z])[A-H](?![A-Z])", answer.upper()))
            if not selected and answer.strip().upper() in labels:
                selected = {answer.strip().upper()}
            missing = sorted(selected - labels)
            if missing:
                risks.append(_review_risk("answer_option_mismatch", "danger", "answer", f"答案引用了不存在的选项：{'、'.join(missing)}。", "检查答案字母和选项分段是否一致。"))
            if "single" in question_type and len(selected) > 1:
                risks.append(_review_risk("choice_type_mismatch", "danger", "question_type", "题目标记为单选题，但答案包含多个选项。", "检查题型是否误识别为单选题，或检查答案是否被错误拼接。"))
            if ("multi" in question_type or "multiple" in question_type) and len(selected) == 1:
                risks.append(_review_risk("question_type_suspect", "warning", "question_type", "题目标记为多选题，但当前答案只包含一个选项。", "检查选项排版和原始识别结果，确认题型及答案是否正确。"))

        if require_knowledge and not _review_text(knowledge):
            risks.append(_review_risk("missing_knowledge", "warning", "knowledge_points", "题目没有知识点。", "让 AI 根据题干和解析补充知识点标签。"))
        if require_source and not _review_text(source):
            risks.append(_review_risk("missing_source", "suggestion", "source", "题目没有试题来源。", "补充试卷名称、年份或导入文件来源。"))

        figure_ids, duplicate_figure_ids = _review_figures(raw)
        references = set(re.findall(r"(?:fig:|image:|图片[:：]?)\s*([A-Za-z0-9_.-]+)", full_text, flags=re.IGNORECASE))
        if duplicate_figure_ids:
            risks.append(_review_risk("duplicate_figure_id", "danger", "figures", f"图片素材 ID 重复：{'、'.join(sorted(set(duplicate_figure_ids)))}。", "保留唯一素材 ID，并重新关联图片。"))
        missing_refs = sorted(references - figure_ids)
        unused_figures = sorted(figure_ids - references)
        if missing_refs:
            risks.append(_review_risk("missing_figure", "danger", "figures", f"题目引用了不存在的图片：{'、'.join(missing_refs)}。", "从素材缓存重新选择图片，或修正图片引用。"))
        if unused_figures:
            risks.append(_review_risk("unused_figure", "warning", "figures", f"存在未被题目内容引用的图片：{'、'.join(unused_figures)}。", "确认图片位置，避免导出时多图或错图。"))

        malformed_display, unbalanced_latex = _latex_delimiter_status(full_text)
        if malformed_display:
            risks.append(_review_risk("malformed_latex", "warning", "latex", "LaTeX 块公式分隔符混用或未完整闭合。", "把 $$...$ 或 $...$$ 修正为完整的 $$...$$，再重新校验。"))
        elif unbalanced_latex:
            risks.append(_review_risk("unbalanced_latex", "warning", "latex", "LaTeX 行内分隔符数量不成对。", "检查 $...$ 或 $$...$$ 的开闭分隔符。"))

        imported_warnings = raw.get("validation_warnings") or raw.get("warnings") or []
        if imported_warnings:
            values = imported_warnings if isinstance(imported_warnings, list) else [imported_warnings]
            for warning in values:
                if _is_informational_import_warning(warning):
                    continue
                risks.append(_review_risk("import_warning", "warning", "question", _preview_text(warning, 240), "根据提示检查原文识别结果。"))

        for risk in risks:
            total_counts[risk["severity"]] += 1
        items.append({
            "question_id": question_id,
            "question_number": index,
            "risk_count": len(risks),
            "risks": risks,
        })

    duplicate_groups = [ids for ids in title_fingerprints.values() if len(ids) > 1]
    if duplicate_groups:
        for group in duplicate_groups:
            for item in items:
                if item["question_id"] in group:
                    risk = _review_risk("duplicate_question", "warning", "title", f"题干与题目 {'、'.join(item_id for item_id in group if item_id != item['question_id'])} 重复。", "确认是否为重复导入；必要时删除或合并题目。")
                    item["risks"].append(risk)
                    item["risk_count"] += 1
                    total_counts["warning"] += 1

    risk_question_count = sum(1 for item in items if item["risk_count"])
    returned_items = [item for item in items if item["risk_count"]] if risks_only else items
    guidance = _review_workflow_guidance(items, str(full.get("task", {}).get("task_id") or task_id).strip())
    return {
        "ok": True,
        "task_id": str(full.get("task", {}).get("task_id") or task_id).strip(),
        "question_count": len(items),
        "returned_question_count": len(returned_items),
        "risks_only": bool(risks_only),
        "risk_question_count": risk_question_count,
        "risk_count": sum(total_counts.values()),
        "summary": total_counts,
        "clean": not any(total_counts.values()),
        "items": returned_items,
        "task_warnings": full.get("task", {}).get("warnings", []),
        "workflow": guidance,
        "message": "未发现结构化风险。" if not any(total_counts.values()) else f"发现 {risk_question_count} 道题存在 {sum(total_counts.values())} 项风险。",
    }


def _legacy_find_duplicate_review_tasks(
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


def _legacy_delete_review_tasks(task_ids: list[str], confirmed: bool = False) -> dict[str, Any]:
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


def _legacy_suggest_knowledge_points_for_task(
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
    result["task_id"] = str(full.get("task", {}).get("task_id") or task_id).strip()
    return result


def _legacy_clean_review_task_latex(
    task_id: str,
    question_ids: list[str] | None = None,
    dry_run: bool = True,
    reason: str | None = None,
    expected_updated_at: str | None = None,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """清理当前校对草稿中的 Markdown 斜体公式。

    默认预览，确认后携带 plan_token 且 dry_run=false 才写入。若仍有 LaTeX 风险，调用方必须
    回读完整题目，并用 update_review_task_draft 逐字段写回标准 LaTeX 格式。
    """
    full = get_review_task_full(task_id)
    if not full.get("ok"):
        return full
    resolved_task_id = str(full.get("task", {}).get("task_id") or task_id).strip()
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

    base_updated_at = str(full.get("task", {}).get("updated_at") or "")
    version_snapshot = {
        "task_id": resolved_task_id,
        "updated_at": base_updated_at,
        "question_ids": sorted(wanted),
        "reason": str(reason or "").strip(),
        "items": changed,
    }
    response = {
        "ok": True,
        "task_id": resolved_task_id,
        "dry_run": dry_run,
        "changed_count": len(changed),
        "replacement_count": total_replacements,
        "items": changed,
        "operation_plan": None,
        "remaining_risks": [],
        "manual_action_required": False,
        "workflow": None,
        "manual_format_guidance": None,
        "message": "预览完成，未写入当前草稿。",
    }
    if dry_run:
        if changed:
            operation_plan = _persisted_operation_plan_payload(
                action="review.latex_cleanup",
                targets=[
                    {"type": "review_question", "id": str(item["question_id"])}
                    for item in changed
                    if str(item.get("question_id") or "").strip()
                ],
                summary=f"清理审核任务 {resolved_task_id} 中 {len(changed)} 道题的 LaTeX 格式。",
                warnings=["执行会写入当前审核草稿；预览后草稿变化时必须重新预览。"],
                version_snapshot=version_snapshot,
                reversible=False,
            )
            response["operation_plan"] = operation_plan
            response["plan_token"] = operation_plan["operation_id"]
            response["requires_confirmation"] = True
        return response

    def execute_cleanup() -> dict[str, Any]:
        if changed:
            try:
                _update_review_task_questions(
                    resolved_task_id,
                    cleaned_questions,
                    changed,
                    kind="latex_cleanup",
                    reason=reason,
                    expected_updated_at=base_updated_at,
                )
            except ReviewTaskConflictError as exc:
                raise OperationPlanVersionConflict(str(exc)) from exc
        remaining = validate_review_task(resolved_task_id, question_ids=question_ids) if changed else None
        remaining_items = (remaining or {}).get("items", []) if isinstance(remaining, dict) else []
        result = {**response, "dry_run": False}
        result.update({
            "remaining_risks": remaining_items,
            "manual_action_required": bool(remaining_items),
            "workflow": (remaining or {}).get("workflow") if isinstance(remaining, dict) else None,
            "manual_format_guidance": (
                {
                    "standard": [
                        "行内公式统一使用 $...$。",
                        "独立成行的块公式统一使用 $$...$$。",
                        "每个开分隔符必须以同类型的闭分隔符结束，不混用 $ 与 $$。",
                    ],
                    "next_steps": [
                        "用 get_review_task_full 读取 remaining_risks 对应题目的完整字段。",
                        "用 update_review_task_draft 为 title、stem、options、answer 或 analysis 生成逐题补丁。",
                        "再次调用 validate_review_task，只在相关风险已消除后报告完成。",
                    ],
                }
                if remaining_items
                else None
            ),
            "message": "已完成自动清洗，但仍有风险需要人工处理。" if remaining_items else "已完成自动清洗，复核未发现剩余风险。",
        })
        return result

    return _execute_persisted_operation(
        plan_token,
        action="review.latex_cleanup",
        version_snapshot_reader=lambda: version_snapshot,
        executor=execute_cleanup,
    )


_MERGED_OPTION_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-H])\s*(?:[\.．、:：]|(?=\s{2,}))\s*",
    flags=re.IGNORECASE,
)


def _merged_option_source(item: dict[str, Any]) -> str:
    for key in ("raw_text", "raw_content", "source_text", "original_text", "content", "stem"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


_OPTION_METADATA_BOUNDARY_RE = re.compile(r"\n\s*(?:【\s*)?(?:答案|解析|详解|难度|知识点)", flags=re.IGNORECASE)


def _extract_option_block(source: str) -> str:
    """Limit OCR option parsing to the quoted option block before answer metadata."""
    source = source or ""
    first_option = re.search(r"(?:^|\n)\s*>\s*[A-H]\s*(?:[\.．、:：]|(?=\s{2,}))", source, flags=re.IGNORECASE)
    if first_option is None:
        return source
    start = first_option.start()
    end_match = _OPTION_METADATA_BOUNDARY_RE.search(source, first_option.end())
    return source[start:end_match.start() if end_match else len(source)]


def _split_merged_option_text(source: str) -> list[tuple[str, str]]:
    option_block = _extract_option_block(source)
    matches = list(_MERGED_OPTION_RE.finditer(option_block))
    if len(matches) < 2:
        return []
    labels = [match.group(1).upper() for match in matches]
    if len(labels) != len(set(labels)):
        return []
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(option_block)
        text = re.sub(r"(?m)^\s*>\s?", "", option_block[match.end():end]).strip(" \t\r\n;；")
        if not text:
            return []
        result.append((labels[index], text))
    return result


def _build_split_options(raw_options: Any, split_options: list[tuple[str, str]]) -> list[dict[str, Any]]:
    template = raw_options[0] if isinstance(raw_options, list) and raw_options and isinstance(raw_options[0], dict) else {}
    if "opt" in template:
        return [{"opt": label, "content": text} for label, text in split_options]
    if "option" in template:
        return [{"option": label, "text": text} for label, text in split_options]
    if "key" in template:
        return [{"key": label, "value": text} for label, text in split_options]
    return [{"label": label, "text": text} for label, text in split_options]


def _legacy_split_merged_options(
    task_id: str,
    question_ids: list[str] | None = None,
    dry_run: bool = True,
    reason: str | None = None,
    expected_updated_at: str | None = None,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """从原始识别文本拆分合并选项；默认预览，执行必须携带 plan_token。"""
    full = get_review_task_full(task_id, question_ids=question_ids, include_knowledge=False)
    if not full.get("ok"):
        return full
    resolved_task_id = str(full.get("task", {}).get("task_id") or task_id).strip()
    questions = full.get("questions") if isinstance(full.get("questions"), list) else []
    wanted = {str(item).strip() for item in (question_ids or []) if str(item).strip()}
    changed: list[dict[str, Any]] = []
    updated_questions: list[Any] = []
    for raw in questions:
        if not isinstance(raw, dict):
            updated_questions.append(raw)
            continue
        qid = str(raw.get("question_id") or raw.get("id") or raw.get("draft_id") or "").strip()
        if wanted and qid not in wanted:
            updated_questions.append(raw)
            continue
        existing = _review_options(raw)
        source = _merged_option_source(raw)
        split_options = _split_merged_option_text(source)
        if len(split_options) < 2 or len(split_options) <= len(existing):
            updated_questions.append(raw)
            continue
        updated = dict(raw)
        raw_options = raw.get("options") if raw.get("options") is not None else raw.get("choices")
        updated["options"] = _build_split_options(raw_options, split_options)
        updated_questions.append(updated)
        changed.append(
            {
                "question_id": qid,
                "source_preview": _preview_text(source, 240),
                "options": [{"label": label, "text": text} for label, text in split_options],
            }
        )

    base_updated_at = str(full.get("task", {}).get("updated_at") or "")
    version_snapshot = {
        "task_id": resolved_task_id,
        "updated_at": base_updated_at,
        "question_ids": sorted(wanted),
        "reason": str(reason or "").strip(),
        "items": changed,
    }
    response = {
        "ok": True,
        "task_id": resolved_task_id,
        "dry_run": dry_run,
        "changed_count": len(changed),
        "items": changed,
        "operation_plan": None,
        "validation": None,
        "remaining_risks": [],
        "manual_action_required": False,
        "workflow": None,
        "message": "预览完成，未写入当前草稿。",
    }
    if dry_run:
        if changed:
            operation_plan = _persisted_operation_plan_payload(
                action="review.split_merged_options",
                targets=[{"type": "review_question", "id": str(item["question_id"])} for item in changed],
                summary=f"拆分审核任务 {resolved_task_id} 中 {len(changed)} 道题的合并选项。",
                warnings=["选项结构会被直接重写；预览后草稿变化时必须重新预览。"],
                version_snapshot=version_snapshot,
                reversible=False,
            )
            response["operation_plan"] = operation_plan
            response["plan_token"] = operation_plan["operation_id"]
            response["requires_confirmation"] = True
        return response

    def execute_split() -> dict[str, Any]:
        if changed:
            try:
                _update_review_task_questions(
                    resolved_task_id,
                    updated_questions,
                    changed,
                    kind="split_merged_options",
                    reason=reason,
                    expected_updated_at=base_updated_at,
                )
            except ReviewTaskConflictError as exc:
                raise OperationPlanVersionConflict(str(exc)) from exc
        validation = validate_review_task(resolved_task_id, question_ids=question_ids) if changed else None
        result = {**response, "dry_run": False, "validation": validation}
        result.update({
            "remaining_risks": (validation or {}).get("items", []) if isinstance(validation, dict) else [],
            "manual_action_required": bool((validation or {}).get("risk_count")) if isinstance(validation, dict) else False,
            "workflow": (validation or {}).get("workflow") if isinstance(validation, dict) else None,
            "message": (
                "已拆分合并选项，但仍有风险需要继续处理。"
                if isinstance(validation, dict) and validation.get("risk_count")
                else "已拆分合并选项并通过复核。"
            ),
        })
        return result

    return _execute_persisted_operation(
        plan_token,
        action="review.split_merged_options",
        version_snapshot_reader=lambda: version_snapshot,
        executor=execute_split,
    )


def _legacy_deduplicate_review_task_questions(
    task_id: str,
    dry_run: bool = True,
    reason: str | None = None,
    expected_updated_at: str | None = None,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """删除当前审核草稿中内容完全一致的重复题；执行必须携带预览返回的 plan_token。

    仅在题型、题干、选项、答案、解析和来源都一致时才判为重复，图片占位符 ID
    的差异不会阻止识别。每组保留导入顺序最靠前的一题。
    """
    full = get_review_task_full(task_id, include_knowledge=False)
    if not full.get("ok"):
        return full
    resolved_task_id = str(full.get("task", {}).get("task_id") or task_id).strip()
    questions = full.get("questions") if isinstance(full.get("questions"), list) else []
    groups: dict[tuple[Any, ...], list[tuple[str, Any]]] = {}
    for raw in questions:
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get("question_id") or raw.get("id") or raw.get("draft_id") or "").strip()
        signature = _review_exact_duplicate_signature(raw)
        if qid and signature is not None:
            groups.setdefault(signature, []).append((qid, raw))

    duplicate_groups = [items for items in groups.values() if len(items) > 1]
    removed_ids = {qid for items in duplicate_groups for qid, _raw in items[1:]}
    kept_ids = {items[0][0] for items in duplicate_groups}
    items = [
        {
            "kept_question_id": entries[0][0],
            "removed_question_ids": [qid for qid, _raw in entries[1:]],
            "count": len(entries),
        }
        for entries in duplicate_groups
    ]
    updated_questions = [
        raw for raw in questions
        if not isinstance(raw, dict)
        or str(raw.get("question_id") or raw.get("id") or raw.get("draft_id") or "").strip() not in removed_ids
    ]
    base_updated_at = str(full.get("task", {}).get("updated_at") or "")
    version_snapshot = {
        "task_id": resolved_task_id,
        "updated_at": base_updated_at,
        "reason": str(reason or "").strip(),
        "items": items,
    }
    response = {
        "ok": True,
        "task_id": resolved_task_id,
        "dry_run": dry_run,
        "duplicate_group_count": len(duplicate_groups),
        "removed_count": len(removed_ids),
        "kept_count": len(kept_ids),
        "remaining_question_count": len(updated_questions),
        "items": items,
        "operation_plan": None,
        "validation": None,
        "remaining_risks": [],
        "message": "重复题预览完成，未写入当前草稿。",
    }
    if dry_run:
        if removed_ids:
            operation_plan = _persisted_operation_plan_payload(
                action="review.deduplicate_questions",
                targets=[
                    {"type": "review_question", "id": str(question_id), "label": "待删除重复题"}
                    for item in items
                    for question_id in item["removed_question_ids"]
                ],
                summary=f"从审核任务 {resolved_task_id} 删除 {len(removed_ids)} 道完全重复的草稿题。",
                warnings=["每个重复组仅保留导入顺序最靠前的题目；预览后草稿变化时必须重新预览。"],
                version_snapshot=version_snapshot,
                reversible=False,
            )
            response["operation_plan"] = operation_plan
            response["plan_token"] = operation_plan["operation_id"]
            response["requires_confirmation"] = True
        return response

    def execute_deduplication() -> dict[str, Any]:
        if removed_ids:
            try:
                _update_review_task_questions(
                    resolved_task_id,
                    updated_questions,
                    items,
                    kind="deduplicate_review_questions",
                    reason=reason,
                    expected_updated_at=base_updated_at,
                )
            except ReviewTaskConflictError as exc:
                raise OperationPlanVersionConflict(str(exc)) from exc
        validation = validate_review_task(resolved_task_id) if removed_ids else None
        result = {**response, "dry_run": False, "validation": validation}
        result.update({
            "remaining_risks": (validation or {}).get("items", []) if isinstance(validation, dict) else [],
            "message": f"已删除 {len(removed_ids)} 道内容完全重复的审核草稿题，保留每组首题。",
        })
        return result

    return _execute_persisted_operation(
        plan_token,
        action="review.deduplicate_questions",
        version_snapshot_reader=lambda: version_snapshot,
        executor=execute_deduplication,
    )


def _legacy_update_review_task_draft(
    task_id: str,
    updates: list[dict[str, Any]],
    dry_run: bool = True,
    reason: str | None = None,
    expected_updated_at: str | None = None,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """按题号更新当前校对草稿；默认预览，执行必须携带 plan_token。"""
    if len(updates) > 100:
        return {"ok": False, "error": "一次最多修改 100 道草稿题。"}
    full = get_review_task_full(task_id)
    if not full.get("ok"):
        return full
    resolved_task_id = str(full.get("task", {}).get("task_id") or task_id).strip()
    allowed_fields = {
        "title",
        "stem",
        "question_body",
        "figures",
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

    changed_items = [item for item in preview_items if item["status"] == "changed"]
    base_updated_at = str(full.get("task", {}).get("updated_at") or "")
    version_snapshot = {
        "task_id": resolved_task_id,
        "updated_at": base_updated_at,
        "reason": str(reason or "").strip(),
        "items": preview_items,
    }
    response = {
        "ok": True,
        "task_id": resolved_task_id,
        "dry_run": dry_run,
        "changed_count": changed_count,
        "items": preview_items,
        "operation_plan": None,
        "validation": None,
        "remaining_risks": [],
        "manual_action_required": False,
        "workflow": None,
        "message": "预览完成，未写入当前草稿。",
    }
    if dry_run:
        if changed_count > 0:
            operation_plan = _persisted_operation_plan_payload(
                action="review.update_draft",
                targets=_question_operation_targets(preview_items),
                summary=f"更新审核任务 {resolved_task_id} 中 {changed_count} 道草稿题。",
                warnings=["执行前应核对题干、选项、答案与解析；预览后草稿变化时必须重新预览。"],
                version_snapshot=version_snapshot,
                reversible=False,
            )
            response["operation_plan"] = operation_plan
            response["plan_token"] = operation_plan["operation_id"]
            response["requires_confirmation"] = True
        return response

    def execute_update() -> dict[str, Any]:
        if changed_count:
            try:
                _update_review_task_questions(
                    resolved_task_id,
                    updated_questions,
                    changed_items,
                    kind="draft_update",
                    reason=reason,
                    expected_updated_at=base_updated_at,
                )
            except ReviewTaskConflictError as exc:
                raise OperationPlanVersionConflict(str(exc)) from exc
        validation = validate_review_task(resolved_task_id) if changed_count else None
        result = {**response, "dry_run": False, "validation": validation}
        result.update({
            "remaining_risks": (validation or {}).get("items", []) if isinstance(validation, dict) else [],
            "manual_action_required": bool((validation or {}).get("risk_count")) if isinstance(validation, dict) else False,
            "workflow": (validation or {}).get("workflow") if isinstance(validation, dict) else None,
            "message": (
                "已更新当前校对草稿，但仍有风险需要继续处理。"
                if isinstance(validation, dict) and validation.get("risk_count")
                else "已更新当前校对草稿并通过复核。"
            ),
        })
        return result

    return _execute_persisted_operation(
        plan_token,
        action="review.update_draft",
        version_snapshot_reader=lambda: version_snapshot,
        executor=execute_update,
    )


def _legacy_list_question_tags(
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


def _legacy_diagnose_tag_maintenance(
    query: str | None = None,
    limit: int = 50,
    min_similarity: float = 0.86,
) -> dict[str, Any]:
    """诊断正式题库标签混乱：近义/重复标签、未使用标签。只读。"""
    try:
        return _diagnose_tag_maintenance(
            query=str(query or "").strip() or None,
            limit=min(max(int(limit or 50), 1), 200),
            min_similarity=max(min(float(min_similarity or 0.86), 1.0), 0.5),
            db_path=_formal_db_path(),
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))


def _legacy_suggest_question_tags(question_ids: list[str]) -> dict[str, Any]:
    """根据方法索引和高置信内容规则，为题目建议可补充的教学标签。只读。"""
    try:
        return _suggest_question_tags(
            question_ids=question_ids,
            db_path=_formal_db_path(),
        )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))


def _legacy_maintain_question_tags(
    question_ids: list[str] | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    merge_map: dict[str, list[str]] | None = None,
    dry_run: bool = True,
    reason: str | None = None,
    create_catalog_tags: bool = True,
) -> dict[str, Any]:
    """新增、删除或合并正式题库标签。默认只预览；dry_run=false 必须填写 reason。"""
    try:
        result = _maintain_question_tags(
            question_ids=question_ids or [],
            add_tags=add_tags or [],
            remove_tags=remove_tags or [],
            merge_map=merge_map or {},
            dry_run=bool(dry_run),
            reason=reason,
            create_catalog_tags=bool(create_catalog_tags),
            db_path=_formal_db_path(),
        )
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if result.get("ok") and dry_run and result.get("changed_count"):
            result["operation_plan"] = _operation_plan_payload(
                action="canonical.tag_maintenance",
                targets=_question_operation_targets(items),
                summary=f"维护 {result['changed_count']} 道正式题的检索标签。",
                warnings=["执行后会刷新相关检索索引。"],
                version_snapshot={"items": items, "merge_map": merge_map or {}},
                reversible=True,
            )
        return result
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        return _tool_error("DATABASE_ERROR", str(exc), retryable=isinstance(exc, sqlite3.OperationalError))


def _legacy_list_change_batches(
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


def _legacy_get_change_batch(batch_id: str) -> dict[str, Any]:
    """读取一个受控变更批次及逐项 diff。只读。"""
    return _change_audit_service().get_batch(batch_id)


def _execute_rollback_change_batch(
    batch_id: str,
    dry_run: bool = True,
    reason: str | None = None,
    allow_conflicts: bool = False,
) -> dict[str, Any]:
    """按审计批次回滚正式库变更。默认只预览；确认后 dry_run=false 才执行。"""
    result = _change_audit_service().rollback_batch(
        batch_id,
        dry_run=dry_run,
        reason=reason,
        allow_conflicts=allow_conflicts,
    )
    if not result.get("ok") or dry_run or result.get("change_type") != "return_to_review":
        return result
    with _connect_formal_write_db() as conn:
        _ensure_review_queue_outbox_schema(conn)
        cursor = conn.execute(
            """
            UPDATE review_queue_outbox
            SET delivery_status = 'cancelled', last_error = 'Cancelled because the change batch was rolled back.'
            WHERE audit_batch_id = ? AND delivery_status != 'delivered'
            """,
            (batch_id,),
        )
        conn.commit()
    result["cancelled_outbox_count"] = cursor.rowcount
    return result


def _legacy_rollback_change_batch(
    batch_id: str,
    dry_run: bool = True,
    reason: str | None = None,
    allow_conflicts: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """预览并以版本绑定令牌回滚审计批次。"""
    def preview_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
        preview = _execute_rollback_change_batch(batch_id, True, reason, allow_conflicts)
        snapshot = {
            "batch_id": batch_id,
            "change_type": preview.get("change_type"),
            "status": preview.get("status"),
            "changed_count": preview.get("changed_count"),
            "conflict_count": preview.get("conflict_count"),
            "items": preview.get("items", []),
            "allow_conflicts": bool(allow_conflicts),
        }
        return preview, snapshot

    preview, snapshot = preview_snapshot()
    if not preview.get("ok"):
        return preview
    if dry_run:
        operation_plan = _persisted_operation_plan_payload(
            action="canonical.rollback_change_batch",
            targets=[{"type": "change_batch", "id": batch_id, "label": str(preview.get("change_type") or "rollback")}],
            summary=f"回滚正式库变更批次 {batch_id}。",
            warnings=["执行前会重新检查逐项当前值；有冲突时默认拒绝回滚。"],
            version_snapshot=snapshot,
            reversible=False,
        )
        return {**preview, "operation_plan": operation_plan, "plan_token": operation_plan["operation_id"], "requires_confirmation": True}
    return _execute_persisted_operation(
        plan_token,
        action="canonical.rollback_change_batch",
        version_snapshot_reader=lambda: preview_snapshot()[1],
        executor=lambda: _execute_rollback_change_batch(batch_id, False, reason, allow_conflicts),
    )


def _legacy_batch_replace_question_tags(
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

            raw_before = _raw_tags(row["tags_json"])
            before = _parse_tags(row["tags_json"])
            after = update_map[question_id]
            # Compare the stored representation as well as its normalized
            # meaning. Otherwise duplicate/whitespace-only corruption is
            # permanently reported by health checks but can never be fixed.
            status = "unchanged" if raw_before == after else "changed"
            if status == "changed":
                changed += 1
            items.append(
                {
                    "question_id": question_id,
                    "title": row["canonical_title"],
                    "question_type": row["question_type"],
                    "difficulty": row["difficulty"],
                    "knowledge_point": row["module"],
                    "before_tags": raw_before,
                    "after_tags": after,
                    "before_value": raw_before,
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
        "operation_plan": (
            _operation_plan_payload(
                action="canonical.batch_replace_tags",
                targets=_question_operation_targets(items),
                summary=f"批量替换 {changed} 道正式题的标签。",
                warnings=[f"{len(missing)} 道题不存在，不会被写入。"] if missing else [],
                version_snapshot=items,
                reversible=True,
            )
            if dry_run and changed > 0
            else None
        ),
        "requires_confirmation": dry_run and changed > 0,
        "message": "预览完成，未写入数据库；确认后才可 dry_run=false。" if dry_run else "已批量替换正式题库标签，并记录审计批次。",
    }


def _execute_return_question_to_review(
    question_id: str,
    reason: str = "题目需要回炉重造",
    dry_run: bool = True,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """受控把正式题库题目打回审核库，并以持久化 outbox 保证可重试投递。"""
    qid = str(question_id or "").strip()
    if not qid:
        return {"ok": False, "error": "question_id 不能为空。"}
    requested_operation_id = str(operation_id or "").strip()
    if requested_operation_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", requested_operation_id):
        return _tool_error("INVALID_ARGUMENT", "operation_id 仅允许字母、数字、下划线和连字符，长度不超过 80。", field="operation_id")

    with _connect_formal_write_db() as conn:
        _ensure_review_queue_outbox_schema(conn)
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

        active_outbox = conn.execute(
            """
            SELECT operation_id, review_id, audit_batch_id, delivery_status
            FROM review_queue_outbox
            WHERE question_id = ? AND delivery_status != 'delivered'
            ORDER BY created_at DESC LIMIT 1
            """,
            (qid,),
        ).fetchone()
        resolved_operation_id = requested_operation_id or (
            str(active_outbox["operation_id"]) if active_outbox is not None else f"RTREV-{_short_id()}"
        )
        existing_outbox = conn.execute(
            """
            SELECT operation_id, review_id, audit_batch_id, delivery_status
            FROM review_queue_outbox WHERE operation_id = ?
            """,
            (resolved_operation_id,),
        ).fetchone()
        review_id = str(existing_outbox["review_id"]) if existing_outbox is not None else f"REV-{_short_id()}"
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
        if dry_run:
            batch_id = None
        elif existing_outbox is not None:
            batch_id = existing_outbox["audit_batch_id"]
        else:
            _ensure_change_audit_schema(conn)
            payload_json = json.dumps(
                {
                    "source": "claude_mcp",
                    "action": "return_to_review",
                    "operation_id": resolved_operation_id,
                },
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
            conn.execute(
                """
                INSERT INTO review_queue_outbox (
                    operation_id, review_id, question_id, reason, payload_json, audit_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (resolved_operation_id, review_id, qid, reason, payload_json, batch_id),
            )
            conn.commit()
    delivery = _deliver_review_queue_outbox(resolved_operation_id) if not dry_run else None

    return {
        "ok": True,
        "dry_run": dry_run,
        "operation_id": resolved_operation_id,
        "canonical_database_path": str(_formal_db_path()),
        "review_database_path": str(_review_db_path()),
        "audit_batch_id": batch_id,
        "delivery_status": delivery["delivery_status"] if delivery else "preview",
        "delivery": delivery,
        "requires_confirmation": dry_run,
        "item": item,
        "message": "预览完成，未写入数据库；确认后才可 dry_run=false。" if dry_run else (
            "已更新正式题库状态，并送入审核库校对队列。" if delivery and delivery.get("ok")
            else "已更新正式题库状态；审核队列将由对账工具重试投递。"
        ),
    }


def _legacy_return_question_to_review(
    question_id: str,
    reason: str = "题目需要回炉重造",
    dry_run: bool = True,
    operation_id: str | None = None,
    plan_token: str | None = None,
) -> dict[str, Any]:
    """预览并以版本绑定令牌把正式题退回审核库。"""
    def preview_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
        preview = _execute_return_question_to_review(question_id, reason, True, operation_id)
        item = preview.get("item") if isinstance(preview.get("item"), dict) else {}
        snapshot = {
            "question_id": str(question_id),
            "reason": reason,
            "before_status": item.get("before_status"),
            "before_review_status": item.get("before_review_status"),
            "before_value": item.get("before_value"),
        }
        return preview, snapshot

    preview, snapshot = preview_snapshot()
    if not preview.get("ok"):
        return preview
    if dry_run:
        operation_plan = _persisted_operation_plan_payload(
            action="canonical.return_question_to_review",
            targets=[{"type": "canonical_question", "id": str(question_id), "label": str(preview.get("item", {}).get("title") or question_id)}],
            summary=f"把正式题 {question_id} 退回审核库。",
            warnings=["执行会更新正式题状态并通过持久化 outbox 投递审核队列。"],
            version_snapshot=snapshot,
            reversible=True,
        )
        return {**preview, "operation_plan": operation_plan, "plan_token": operation_plan["operation_id"], "requires_confirmation": True}
    resolved_operation_id = str(operation_id or "").strip() or f"RTREV-{str(plan_token or '')[-12:]}"
    return _execute_persisted_operation(
        plan_token,
        action="canonical.return_question_to_review",
        version_snapshot_reader=lambda: preview_snapshot()[1],
        executor=lambda: _execute_return_question_to_review(question_id, reason, False, resolved_operation_id),
    )


def _legacy_reconcile_review_queue_outbox(limit: int = 20) -> dict[str, Any]:
    """重试投递尚未进入审核库的正式题库回炉操作。不会重复修改正式题目。"""
    safe_limit = min(max(int(limit or 20), 1), 100)
    with _connect_formal_write_db() as conn:
        _ensure_review_queue_outbox_schema(conn)
        rows = conn.execute(
            """
            SELECT operation_id FROM review_queue_outbox
            WHERE delivery_status = 'pending'
            ORDER BY created_at ASC LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        conn.commit()
    deliveries = [_deliver_review_queue_outbox(str(row["operation_id"])) for row in rows]
    delivered = sum(1 for item in deliveries if item.get("delivery_status") == "delivered")
    return {
        "ok": all(item.get("ok") for item in deliveries),
        "attempted_count": len(deliveries),
        "delivered_count": delivered,
        "pending_count": len(deliveries) - delivered,
        "items": deliveries,
    }


def _legacy_batch_replace_question_knowledge_points(
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
        "operation_plan": (
            _operation_plan_payload(
                action="canonical.batch_replace_knowledge_points",
                targets=_question_operation_targets(items),
                summary=f"替换 {changed_count} 道正式题的知识目录绑定。",
                warnings=[f"{len(missing_questions)} 道题不存在，不会被写入。"] if missing_questions else [],
                version_snapshot=items,
                reversible=True,
            )
            if dry_run and changed_count > 0
            else None
        ),
        "items": items,
        "reason": reason,
        "message": "预览完成，未写入数据库；确认后才可 dry_run=false。" if dry_run else "已批量更新正式题库知识目录绑定，并记录审计批次。",
    }


def _legacy_find_similar_questions(
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


def _canonical_duplicate_candidates(
    *,
    prefer_persisted_hashes: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build conservative exact-duplicate groups from canonical question content."""
    # Once the canonical hashes have been backfilled, a duplicate scan does
    # not need to normalise every stem and option again.  Keep the complete
    # calculation as the fallback for an incomplete or legacy database, so a
    # scan remains correct before the one-time backfill has happened.
    if prefer_persisted_hashes:
        with _connect_formal_read_db() as conn:
            rows = conn.execute(
                """
                SELECT q.question_id, q.question_type, q.status, q.created_at, q.content_hash,
                       qti.title_text, qti.stem_text, qti.options_json, qti.answer_text,
                       qti.source_text
                FROM questions q
                JOIN question_text_index qti ON qti.question_id = q.question_id
                """
            ).fetchall()
        by_fingerprint: dict[str, list[dict[str, Any]]] = {}
        hash_updates: list[dict[str, Any]] = []
        for row in rows:
            fingerprint = str(row["content_hash"] or "").strip()
            if not fingerprint:
                fingerprint = canonical_question_fingerprint(
                    question_type=row["question_type"],
                    title=row["title_text"],
                    stem=row["stem_text"],
                    options=row["options_json"],
                    answer=row["answer_text"],
                ) or ""
                if fingerprint:
                    hash_updates.append(
                        {
                            "question_id": str(row["question_id"]),
                            "before_value": None,
                            "after_value": fingerprint,
                            "status": "changed",
                        }
                    )
            if not fingerprint:
                continue
            by_fingerprint.setdefault(fingerprint, []).append(
                {
                    "question_id": str(row["question_id"]),
                    "title": str(row["title_text"] or ""),
                    "status": str(row["status"] or ""),
                    "source": str(row["source_text"] or ""),
                    "created_at": str(row["created_at"] or ""),
                }
            )
        return _canonical_duplicate_groups_from_members(by_fingerprint), hash_updates

    with _connect_formal_read_db() as conn:
        rows = conn.execute(
            """
            SELECT q.question_id, q.question_type, q.status, q.created_at, q.content_hash,
                   qti.title_text, qti.stem_text, qti.options_json, qti.answer_text,
                   qti.source_text
            FROM questions q
            JOIN question_text_index qti ON qti.question_id = q.question_id
            """
        ).fetchall()
    by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    hash_updates: list[dict[str, Any]] = []
    for row in rows:
        fingerprint = canonical_question_fingerprint(
            question_type=row["question_type"],
            title=row["title_text"],
            stem=row["stem_text"],
            options=row["options_json"],
            answer=row["answer_text"],
        )
        if not fingerprint:
            continue
        item = {
            "question_id": str(row["question_id"]),
            "title": str(row["title_text"] or ""),
            "status": str(row["status"] or ""),
            "source": str(row["source_text"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        by_fingerprint.setdefault(fingerprint, []).append(item)
        existing_hash = str(row["content_hash"] or "")
        if existing_hash != fingerprint:
            hash_updates.append({
                "question_id": item["question_id"],
                "before_value": existing_hash or None,
                "after_value": fingerprint,
                "status": "changed",
            })
    groups = _canonical_duplicate_groups_from_members(by_fingerprint)
    return groups, hash_updates


def _canonical_duplicate_groups_from_members(
    by_fingerprint: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for fingerprint, members in by_fingerprint.items():
        if len(members) < 2:
            continue
        ordered_members = sorted(members, key=lambda item: (item["created_at"], item["question_id"]))
        groups.append(
            {
                "group_id": f"DUP-{fingerprint[:12]}",
                "content_hash": fingerprint,
                "recommended_primary_question_id": ordered_members[0]["question_id"],
                "duplicate_question_ids": [item["question_id"] for item in ordered_members[1:]],
                "members": ordered_members,
                "member_count": len(ordered_members),
            }
        )
    groups.sort(key=lambda item: (-int(item["member_count"]), item["group_id"]))
    return groups


def _ensure_canonical_duplicate_archive_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS canonical_duplicate_archives (
            archive_id TEXT PRIMARY KEY,
            merge_batch_id TEXT NOT NULL,
            primary_question_id TEXT NOT NULL,
            duplicate_question_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            previous_status TEXT,
            previous_review_comment TEXT,
            primary_tags_before_json TEXT NOT NULL DEFAULT '[]',
            primary_tags_after_json TEXT NOT NULL DEFAULT '[]',
            moved_source_ids_json TEXT NOT NULL DEFAULT '[]',
            added_knowledge_link_ids_json TEXT NOT NULL DEFAULT '[]',
            added_asset_link_ids_json TEXT NOT NULL DEFAULT '[]',
            state TEXT NOT NULL DEFAULT 'archived',
            reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            restored_at TEXT,
            restore_reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_canonical_duplicate_archives_batch
            ON canonical_duplicate_archives(merge_batch_id, state);
        CREATE INDEX IF NOT EXISTS idx_canonical_duplicate_archives_primary
            ON canonical_duplicate_archives(primary_question_id, state);
        """
    )


def _canonical_duplicate_merge_plan(
    primary_question_id: str,
    duplicate_question_ids: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    primary_id = str(primary_question_id or "").strip()
    duplicate_ids = list(dict.fromkeys(str(item).strip() for item in duplicate_question_ids if str(item).strip()))
    if not primary_id:
        return None, _tool_error("INVALID_ARGUMENT", "primary_question_id 不能为空。", field="primary_question_id")
    if not duplicate_ids:
        return None, _tool_error("INVALID_ARGUMENT", "duplicate_question_ids 不能为空。", field="duplicate_question_ids")
    if primary_id in duplicate_ids:
        return None, _tool_error("INVALID_ARGUMENT", "主题题不能同时出现在重复题列表中。", field="duplicate_question_ids")

    with _connect_formal_read_db() as conn:
        placeholders = ",".join("?" for _ in [primary_id, *duplicate_ids])
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.question_type, q.status, q.review_comment, q.created_at,
                   qti.title_text, qti.stem_text, qti.options_json, qti.answer_text, qti.tags_json
            FROM questions q
            JOIN question_text_index qti ON qti.question_id = q.question_id
            WHERE q.question_id IN ({placeholders})
            """,
            [primary_id, *duplicate_ids],
        ).fetchall()
        by_id = {str(row["question_id"]): row for row in rows}
        if primary_id not in by_id:
            return None, _tool_error("QUESTION_NOT_FOUND", f"主题题不存在：{primary_id}。", field="primary_question_id")
        missing_ids = [item for item in duplicate_ids if item not in by_id]
        if missing_ids:
            return None, _tool_error("QUESTION_NOT_FOUND", f"重复题不存在：{'、'.join(missing_ids)}。", field="duplicate_question_ids")

        def fingerprint(row: sqlite3.Row) -> str | None:
            return canonical_question_fingerprint(
                question_type=row["question_type"], title=row["title_text"], stem=row["stem_text"],
                options=row["options_json"], answer=row["answer_text"],
            )

        primary_row = by_id[primary_id]
        primary_hash = fingerprint(primary_row)
        if not primary_hash:
            return None, _tool_error("DUPLICATE_SIGNATURE_INCOMPLETE", "主题题关键信息不足，不能安全合并。", field="primary_question_id")
        non_matching = [item for item in duplicate_ids if fingerprint(by_id[item]) != primary_hash]
        if non_matching:
            return None, _tool_error(
                "DUPLICATE_SIGNATURE_MISMATCH",
                f"这些题与主题题不是完全重复，不能合并：{'、'.join(non_matching)}。",
                field="duplicate_question_ids",
            )
        already_archived = (
            conn.execute(
                f"""
                SELECT duplicate_question_id FROM canonical_duplicate_archives
                WHERE duplicate_question_id IN ({','.join('?' for _ in duplicate_ids)}) AND state = 'archived'
                """,
                duplicate_ids,
            ).fetchall()
            if _table_exists(conn, "canonical_duplicate_archives")
            else []
        )
        if already_archived:
            ids = [str(row["duplicate_question_id"]) for row in already_archived]
            return None, _tool_error("DUPLICATE_ALREADY_ARCHIVED", f"这些重复题已归档：{'、'.join(ids)}。")

        primary_tags = _parse_tags(primary_row["tags_json"])
        merged_tags = list(primary_tags)
        for duplicate_id in duplicate_ids:
            for tag in _parse_tags(by_id[duplicate_id]["tags_json"]):
                if tag not in merged_tags:
                    merged_tags.append(tag)

        primary_topics = {
            str(row["topic3_id"])
            for row in conn.execute("SELECT topic3_id FROM question_knowledge_points WHERE question_id = ?", (primary_id,)).fetchall()
        }
        planned_topics: list[str] = []
        skipped_topics: list[str] = []
        for duplicate_id in duplicate_ids:
            for row in conn.execute(
                "SELECT topic3_id FROM question_knowledge_points WHERE question_id = ? ORDER BY rank", (duplicate_id,)
            ).fetchall():
                topic_id = str(row["topic3_id"])
                if topic_id in primary_topics or topic_id in planned_topics or topic_id in skipped_topics:
                    continue
                if len(primary_topics) + len(planned_topics) < 3:
                    planned_topics.append(topic_id)
                else:
                    skipped_topics.append(topic_id)

        primary_assets = {
            str(row["asset_id"])
            for row in conn.execute("SELECT asset_id FROM question_assets WHERE question_id = ?", (primary_id,)).fetchall()
        } if _table_exists(conn, "question_assets") else set()
        planned_assets: list[str] = []
        if _table_exists(conn, "question_assets"):
            for duplicate_id in duplicate_ids:
                for row in conn.execute("SELECT asset_id FROM question_assets WHERE question_id = ? ORDER BY sort_order", (duplicate_id,)).fetchall():
                    asset_id = str(row["asset_id"])
                    if asset_id not in primary_assets and asset_id not in planned_assets:
                        planned_assets.append(asset_id)

        source_count = 0
        if _table_exists(conn, "question_sources"):
            source_count = int(conn.execute(
                f"SELECT COUNT(*) FROM question_sources WHERE question_id IN ({','.join('?' for _ in duplicate_ids)})", duplicate_ids
            ).fetchone()[0])

    return {
        "primary_question_id": primary_id,
        "duplicate_question_ids": duplicate_ids,
        "content_hash": primary_hash,
        "primary_tags_before": primary_tags,
        "primary_tags_after": merged_tags,
        "knowledge_topic3_ids_to_add": planned_topics,
        "knowledge_topic3_ids_not_merged_due_to_limit": skipped_topics,
        "asset_ids_to_add": planned_assets,
        "source_records_to_reassign": source_count,
        "items": [
            {
                "question_id": duplicate_id,
                "before_status": by_id[duplicate_id]["status"],
                "before_review_comment": by_id[duplicate_id]["review_comment"],
                "after_status": "archived_duplicate",
                "status": "changed",
            }
            for duplicate_id in duplicate_ids
        ],
    }, None


def _legacy_scan_canonical_duplicate_questions(limit: int = 100) -> dict[str, Any]:
    """扫描正式题库的完全重复候选；只读，不删除、不归档、不修改题目。"""
    safe_limit = min(max(int(limit or 100), 1), 500)
    groups, hash_updates = _canonical_duplicate_candidates(prefer_persisted_hashes=True)
    return {
        "ok": True,
        "database_scope": "canonical_read_only",
        "match_rule": "题型、题干、选项和答案规范化后完全一致；解析与来源不参与判重。",
        "group_count": len(groups),
        "duplicate_question_count": sum(int(group["member_count"]) - 1 for group in groups),
        "content_hash_backfill_count": sum(1 for item in hash_updates if not item.get("before_value")),
        "stale_content_hash_count": sum(1 for item in hash_updates if item.get("before_value")),
        "groups": groups[:safe_limit],
        "next_step": "先人工核对每组，再决定保留题；调用 backfill_canonical_question_hashes 可让后续入库自动拦截同一内容。",
    }


def _legacy_backfill_canonical_question_hashes(
    dry_run: bool = True,
    reason: str = "为正式题库建立重复题内容指纹",
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    """为正式题库回填内容指纹；可选择重算旧规则产生的既有指纹。"""
    _groups, candidates = _canonical_duplicate_candidates()
    stale_updates = [item for item in candidates if item.get("before_value")]
    updates = candidates if overwrite_existing else [item for item in candidates if not item.get("before_value")]
    preview = {
        "ok": True,
        "database_scope": "canonical",
        "dry_run": dry_run,
        "overwrite_existing": overwrite_existing,
        "changed_count": len(updates),
        "stale_existing_count": len(stale_updates),
        "requires_confirmation": dry_run and bool(updates),
        "items": updates[:100],
        "message": (
            "预览完成，未写入正式题库。"
            if dry_run else "已回填正式题库内容指纹；后续同内容入库会被自动拦截。"
        ),
    }
    if dry_run or not updates:
        return preview

    with _connect_formal_write_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_change_audit_schema(conn)
        for item in updates:
            conn.execute(
                """
                UPDATE questions
                SET content_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE question_id = ?
                """,
                (item["after_value"], item["question_id"]),
            )
        batch_id = _record_change_batch(
            conn,
            change_type="content_hash_backfill",
            reason=reason,
            items=updates,
            field_name="questions.content_hash",
            risk_level="low",
        )
        conn.commit()
    return {**preview, "audit_batch_id": batch_id}


def _execute_merge_canonical_duplicate_questions(
    primary_question_id: str,
    duplicate_question_ids: list[str],
    dry_run: bool = True,
    reason: str = "合并正式题库完全重复题",
) -> dict[str, Any]:
    """合并正式题库完全重复题：保留主题题，汇集关联信息，并软归档重复题。"""
    plan, error = _canonical_duplicate_merge_plan(primary_question_id, duplicate_question_ids)
    if error:
        return error
    assert plan is not None
    result = {
        "ok": True,
        "database_scope": "canonical",
        "dry_run": dry_run,
        "requires_confirmation": dry_run,
        "merge_plan": plan,
        "operation_plan": (
            _operation_plan_payload(
                action="canonical.merge_duplicate_questions",
                targets=[
                    {"type": "canonical_question", "id": str(plan["primary_question_id"]), "label": "保留题"},
                    *[
                        {"type": "canonical_question", "id": str(question_id), "label": "待归档重复题"}
                        for question_id in plan["duplicate_question_ids"]
                    ],
                ],
                summary=(
                    f"保留题 {plan['primary_question_id']}，合并并软归档 "
                    f"{len(plan['duplicate_question_ids'])} 道重复题。"
                ),
                warnings=[str(item) for item in plan.get("warnings", [])],
                version_snapshot=plan,
                reversible=True,
            )
            if dry_run
            else None
        ),
        "message": "预览完成，尚未修改正式题库。" if dry_run else "已合并关联信息并软归档重复题；可用 restore_canonical_duplicate_merge 恢复。",
    }
    if dry_run:
        return result

    with _connect_formal_write_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_canonical_duplicate_archive_schema(conn)
        duplicate_ids = list(plan["duplicate_question_ids"])
        existing_archives = conn.execute(
            f"SELECT duplicate_question_id FROM canonical_duplicate_archives WHERE duplicate_question_id IN ({','.join('?' for _ in duplicate_ids)}) AND state = 'archived'",
            duplicate_ids,
        ).fetchall()
        if existing_archives:
            conn.rollback()
            return _tool_error(
                "DUPLICATE_ALREADY_ARCHIVED",
                f"这些重复题已归档：{'、'.join(str(row['duplicate_question_id']) for row in existing_archives)}。",
            )

        batch_id = _record_change_batch(
            conn,
            change_type="canonical_duplicate_merge",
            reason=reason,
            items=[
                {
                    "question_id": item["question_id"],
                    "before_value": {"status": item["before_status"], "review_comment": item["before_review_comment"]},
                    "after_value": {"status": "archived_duplicate", "primary_question_id": plan["primary_question_id"]},
                    "status": "changed",
                }
                for item in plan["items"]
            ],
            field_name="questions.status",
            risk_level="high",
        )
        primary_id = str(plan["primary_question_id"])
        primary_tags_before = list(plan["primary_tags_before"])
        primary_tags_after = list(plan["primary_tags_after"])
        if primary_tags_before != primary_tags_after:
            conn.execute(
                "UPDATE question_text_index SET tags_json = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (json.dumps(primary_tags_after, ensure_ascii=False), primary_id),
            )

        primary_topics = {
            str(row["topic3_id"])
            for row in conn.execute("SELECT topic3_id FROM question_knowledge_points WHERE question_id = ?", (primary_id,)).fetchall()
        }
        next_rank = int(conn.execute(
            "SELECT COALESCE(MAX(rank), 0) FROM question_knowledge_points WHERE question_id = ?", (primary_id,)
        ).fetchone()[0]) + 1
        added_knowledge_links: list[str] = []
        for topic_id in plan["knowledge_topic3_ids_to_add"]:
            if topic_id in primary_topics or next_rank > 3:
                continue
            link_id = f"QKP-{primary_id}-{next_rank}-{_short_id()}"
            conn.execute(
                """
                INSERT INTO question_knowledge_points
                    (link_id, question_id, topic3_id, rank, source, confidence, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'duplicate_merge', 1.0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (link_id, primary_id, topic_id, next_rank, f"Merged from duplicate batch {batch_id}"),
            )
            added_knowledge_links.append(link_id)
            primary_topics.add(topic_id)
            next_rank += 1

        added_asset_links: list[str] = []
        if _table_exists(conn, "question_assets"):
            existing_assets = {
                str(row["asset_id"])
                for row in conn.execute("SELECT asset_id FROM question_assets WHERE question_id = ?", (primary_id,)).fetchall()
            }
            next_asset_order = int(conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) FROM question_assets WHERE question_id = ?", (primary_id,)
            ).fetchone()[0]) + 1
            for duplicate_id in duplicate_ids:
                asset_rows = conn.execute(
                    """
                    SELECT asset_id, role, placeholder_key, is_primary, is_verified
                    FROM question_assets WHERE question_id = ? ORDER BY sort_order, link_id
                    """,
                    (duplicate_id,),
                ).fetchall()
                for asset_row in asset_rows:
                    asset_id = str(asset_row["asset_id"])
                    if asset_id in existing_assets:
                        continue
                    link_id = f"QAS-{primary_id}-{_short_id()}"
                    conn.execute(
                        """
                        INSERT INTO question_assets
                            (link_id, question_id, asset_id, role, sort_order, placeholder_key, is_primary, is_verified, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                        (link_id, primary_id, asset_id, asset_row["role"], next_asset_order, asset_row["placeholder_key"], asset_row["is_verified"]),
                    )
                    added_asset_links.append(link_id)
                    existing_assets.add(asset_id)
                    next_asset_order += 1

        moved_sources: dict[str, list[str]] = {duplicate_id: [] for duplicate_id in duplicate_ids}
        if _table_exists(conn, "question_sources"):
            source_rows = conn.execute(
                f"SELECT source_id, question_id FROM question_sources WHERE question_id IN ({','.join('?' for _ in duplicate_ids)})",
                duplicate_ids,
            ).fetchall()
            for row in source_rows:
                source_id = str(row["source_id"])
                duplicate_id = str(row["question_id"])
                conn.execute("UPDATE question_sources SET question_id = ?, updated_at = CURRENT_TIMESTAMP WHERE source_id = ?", (primary_id, source_id))
                moved_sources[duplicate_id].append(source_id)

        for item in plan["items"]:
            duplicate_id = str(item["question_id"])
            conn.execute(
                """
                UPDATE questions
                SET status = 'archived_duplicate',
                    review_comment = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE question_id = ?
                """,
                (f"Duplicate of {primary_id}; merge batch {batch_id}", duplicate_id),
            )
            conn.execute(
                """
                INSERT INTO canonical_duplicate_archives (
                    archive_id, merge_batch_id, primary_question_id, duplicate_question_id, content_hash,
                    previous_status, previous_review_comment, primary_tags_before_json, primary_tags_after_json,
                    moved_source_ids_json, added_knowledge_link_ids_json, added_asset_link_ids_json, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"DUPARC-{_short_id()}", batch_id, primary_id, duplicate_id, plan["content_hash"],
                    item["before_status"], item["before_review_comment"],
                    json.dumps(primary_tags_before, ensure_ascii=False), json.dumps(primary_tags_after, ensure_ascii=False),
                    json.dumps(moved_sources[duplicate_id], ensure_ascii=False),
                    json.dumps(added_knowledge_links, ensure_ascii=False), json.dumps(added_asset_links, ensure_ascii=False), reason,
                ),
            )
        conn.commit()
    return {**result, "audit_batch_id": batch_id, "archived_count": len(duplicate_ids)}


def _legacy_merge_canonical_duplicate_questions(
    primary_question_id: str,
    duplicate_question_ids: list[str],
    dry_run: bool = True,
    reason: str = "合并正式题库完全重复题",
    plan_token: str | None = None,
) -> dict[str, Any]:
    """预览并以版本绑定令牌合并正式题库重复题。"""
    def preview_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
        preview = _execute_merge_canonical_duplicate_questions(primary_question_id, duplicate_question_ids, True, reason)
        return preview, dict(preview.get("merge_plan") or {})

    preview, snapshot = preview_snapshot()
    if not preview.get("ok"):
        return preview
    if dry_run:
        merge_plan = preview["merge_plan"]
        operation_plan = _persisted_operation_plan_payload(
            action="canonical.merge_duplicate_questions",
            targets=[
                {"type": "canonical_question", "id": str(merge_plan["primary_question_id"]), "label": "保留题"},
                *[
                    {"type": "canonical_question", "id": str(question_id), "label": "待归档重复题"}
                    for question_id in merge_plan["duplicate_question_ids"]
                ],
            ],
            summary=f"保留题 {merge_plan['primary_question_id']}，合并并软归档 {len(merge_plan['duplicate_question_ids'])} 道重复题。",
            warnings=[str(item) for item in merge_plan.get("warnings", [])],
            version_snapshot=snapshot,
            reversible=True,
        )
        return {**preview, "operation_plan": operation_plan, "plan_token": operation_plan["operation_id"], "requires_confirmation": True}
    return _execute_persisted_operation(
        plan_token,
        action="canonical.merge_duplicate_questions",
        version_snapshot_reader=lambda: preview_snapshot()[1],
        executor=lambda: _execute_merge_canonical_duplicate_questions(primary_question_id, duplicate_question_ids, False, reason),
    )


def _execute_restore_canonical_duplicate_merge(
    merge_batch_id: str,
    dry_run: bool = True,
    reason: str = "恢复重复题合并",
) -> dict[str, Any]:
    """恢复一次正式题库重复题合并：撤销软归档并还原该批次移动的关联。"""
    batch_id = str(merge_batch_id or "").strip()
    if not batch_id:
        return _tool_error("INVALID_ARGUMENT", "merge_batch_id 不能为空。", field="merge_batch_id")
    with _connect_formal_read_db() as conn:
        if not _table_exists(conn, "canonical_duplicate_archives"):
            return _tool_error("MERGE_BATCH_NOT_FOUND", "没有可恢复的重复题合并批次。", field="merge_batch_id")
        rows = conn.execute(
            "SELECT * FROM canonical_duplicate_archives WHERE merge_batch_id = ? AND state = 'archived' ORDER BY created_at DESC, archive_id DESC",
            (batch_id,),
        ).fetchall()
    if not rows:
        return _tool_error("MERGE_BATCH_NOT_FOUND", f"不存在可恢复的合并批次：{batch_id}。", field="merge_batch_id")
    preview_items = [
        {
            "question_id": str(row["duplicate_question_id"]),
            "before_status": "archived_duplicate",
            "after_status": row["previous_status"],
            "status": "will_restore",
        }
        for row in rows
    ]
    result = {
        "ok": True,
        "database_scope": "canonical",
        "merge_batch_id": batch_id,
        "dry_run": dry_run,
        "requires_confirmation": dry_run,
        "items": preview_items,
        "message": "预览完成，尚未恢复。" if dry_run else "已恢复该批次归档的重复题和关联信息。",
    }
    if dry_run:
        return result

    with _connect_formal_write_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for row in rows:
            duplicate_id = str(row["duplicate_question_id"])
            conn.execute(
                "UPDATE questions SET status = ?, review_comment = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ? AND status = 'archived_duplicate'",
                (row["previous_status"], row["previous_review_comment"], duplicate_id),
            )
            source_ids = _decode_json_list(row["moved_source_ids_json"])
            if source_ids and _table_exists(conn, "question_sources"):
                conn.execute(
                    f"UPDATE question_sources SET question_id = ?, updated_at = CURRENT_TIMESTAMP WHERE source_id IN ({','.join('?' for _ in source_ids)})",
                    [duplicate_id, *source_ids],
                )
        first = rows[-1]
        primary_id = str(first["primary_question_id"])
        tags_after = str(rows[0]["primary_tags_after_json"])
        tags_before = str(first["primary_tags_before_json"])
        current_tags = conn.execute("SELECT tags_json FROM question_text_index WHERE question_id = ?", (primary_id,)).fetchone()
        if current_tags is not None and str(current_tags["tags_json"] or "[]") == tags_after:
            conn.execute("UPDATE question_text_index SET tags_json = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?", (tags_before, primary_id))
        link_ids = list(dict.fromkeys(
            str(link_id)
            for row in rows
            for link_id in _decode_json_list(row["added_knowledge_link_ids_json"])
            if str(link_id)
        ))
        if link_ids:
            conn.execute(f"DELETE FROM question_knowledge_points WHERE link_id IN ({','.join('?' for _ in link_ids)})", link_ids)
        asset_link_ids = list(dict.fromkeys(
            str(link_id)
            for row in rows
            for link_id in _decode_json_list(row["added_asset_link_ids_json"])
            if str(link_id)
        ))
        if asset_link_ids and _table_exists(conn, "question_assets"):
            conn.execute(f"DELETE FROM question_assets WHERE link_id IN ({','.join('?' for _ in asset_link_ids)})", asset_link_ids)
        conn.execute(
            "UPDATE canonical_duplicate_archives SET state = 'restored', restored_at = CURRENT_TIMESTAMP, restore_reason = ? WHERE merge_batch_id = ? AND state = 'archived'",
            (reason, batch_id),
        )
        conn.commit()
    return result


def _legacy_restore_canonical_duplicate_merge(
    merge_batch_id: str,
    dry_run: bool = True,
    reason: str = "恢复重复题合并",
    plan_token: str | None = None,
) -> dict[str, Any]:
    """预览并以版本绑定令牌恢复重复题合并。"""
    def preview_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
        preview = _execute_restore_canonical_duplicate_merge(merge_batch_id, True, reason)
        snapshot = {
            "merge_batch_id": str(merge_batch_id),
            "items": preview.get("items", []),
        }
        return preview, snapshot

    preview, snapshot = preview_snapshot()
    if not preview.get("ok"):
        return preview
    if dry_run:
        operation_plan = _persisted_operation_plan_payload(
            action="canonical.restore_duplicate_merge",
            targets=[{"type": "duplicate_merge_batch", "id": str(merge_batch_id), "label": "restore"}],
            summary=f"恢复正式题库重复题合并批次 {merge_batch_id}。",
            warnings=["恢复会撤销软归档，并还原该批次移动的关联信息。"],
            version_snapshot=snapshot,
            reversible=True,
        )
        return {**preview, "operation_plan": operation_plan, "plan_token": operation_plan["operation_id"], "requires_confirmation": True}
    return _execute_persisted_operation(
        plan_token,
        action="canonical.restore_duplicate_merge",
        version_snapshot_reader=lambda: preview_snapshot()[1],
        executor=lambda: _execute_restore_canonical_duplicate_merge(merge_batch_id, False, reason),
    )


def _legacy_list_canonical_duplicate_merges(
    state: Literal["archived", "restored", "all"] = "archived",
    limit: int = 50,
) -> dict[str, Any]:
    """列出正式题库重复题合并批次、主题题和可恢复状态；只读。"""
    safe_limit = min(max(int(limit or 50), 1), 200)
    with _connect_formal_read_db() as conn:
        if not _table_exists(conn, "canonical_duplicate_archives"):
            return {"ok": True, "database_scope": "canonical_read_only", "items": [], "total": 0}
        params: list[Any] = []
        where = ""
        if state != "all":
            where = "WHERE state = ?"
            params.append(state)
        rows = conn.execute(
            f"""
            SELECT merge_batch_id, primary_question_id, state, reason, created_at, restored_at, restore_reason,
                   GROUP_CONCAT(duplicate_question_id, ',') AS duplicate_question_ids
            FROM canonical_duplicate_archives
            {where}
            GROUP BY merge_batch_id, primary_question_id, state, reason, created_at, restored_at, restore_reason
            ORDER BY created_at DESC, merge_batch_id DESC
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()
    items = [
        {
            "merge_batch_id": str(row["merge_batch_id"]),
            "primary_question_id": str(row["primary_question_id"]),
            "duplicate_question_ids": [item for item in str(row["duplicate_question_ids"] or "").split(",") if item],
            "state": str(row["state"]),
            "reason": row["reason"],
            "created_at": row["created_at"],
            "restored_at": row["restored_at"],
            "restore_reason": row["restore_reason"],
        }
        for row in rows
    ]
    return {"ok": True, "database_scope": "canonical_read_only", "items": items, "total": len(items), "limit": safe_limit}


def _legacy_submit_ai_generated_review(
    source_text: str,
    source: str = "Claude Code MCP",
    chat_context: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """把 AI 生成的试题文本提交到审核工作台草稿。只写草稿，不写正式题库。"""
    # Large trusted imports are prepared locally as JSON.  Accepting a
    # project-relative file reference keeps the MCP request small while the
    # actual write still goes through the normal review-workbench service.
    # This is intentionally limited to the project tree; arbitrary file reads
    # are not permitted through this shortcut.
    file_prefix = "@file:"
    if source_text.startswith(file_prefix):
        candidate = (ROOT / source_text.removeprefix(file_prefix).strip()).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError("导入文件必须位于项目目录内") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"导入文件不存在: {candidate}")
        source_text = candidate.read_text(encoding="utf-8")
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


def _legacy_submit_import_job(
    batch_id: str,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """为已有导入批次提交识别任务。返回简短任务摘要；重复请求由正式任务 service 幂等处理。"""
    bid = str(batch_id or "").strip()
    if not bid:
        return {"ok": False, "error": "batch_id 不能为空。"}
    try:
        task, audit_id = _task_center_service().submit_batch_job(
            "recognize",
            bid,
            context=_task_action_context(source, session_id, operator, trace_id=trace_id),
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


def _legacy_submit_ai_clean_job(
    batch_id: str,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """为已有导入批次提交 AI 清洗任务。返回简短任务摘要。"""
    bid = str(batch_id or "").strip()
    if not bid:
        return {"ok": False, "error": "batch_id 不能为空。"}
    try:
        task, audit_id = _task_center_service().submit_batch_job(
            "ai_clean",
            bid,
            context=_task_action_context(source, session_id, operator, trace_id=trace_id),
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


def _legacy_submit_word_export_job(
    lesson_package: dict[str, Any],
    include_answers: bool | None = None,
    include_analysis: bool | None = None,
    file_name: str | None = None,
    template_id: str | None = None,
    format_spec: dict[str, Any] | None = None,
    answer_position: Literal["after_question", "end"] | None = None,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """提交服务端 Word 导出任务；仅返回任务 ID、摘要和下载地址。"""
    return _submit_export_job(
        "word",
        lesson_package,
        include_answers=include_answers,
        include_analysis=include_analysis,
        file_name=file_name,
        template_id=template_id,
        format_spec=format_spec,
        answer_position=answer_position,
        context=_task_action_context(source, session_id, operator, trace_id=trace_id),
    )


def _legacy_submit_pptx_export_job(
    lesson_package: dict[str, Any],
    include_answers: bool = False,
    include_analysis: bool = False,
    file_name: str | None = None,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """提交服务端 PPTX 导出任务；仅返回任务 ID、摘要和下载地址。"""
    return _submit_export_job(
        "pptx",
        lesson_package,
        include_answers=include_answers,
        include_analysis=include_analysis,
        file_name=file_name,
        context=_task_action_context(source, session_id, operator, trace_id=trace_id),
    )


def _legacy_get_job_status(task_id: str) -> dict[str, Any]:
    """查询单个后台任务状态。只读。"""
    tid = str(task_id or "").strip()
    if not tid:
        return _tool_error("INVALID_ARGUMENT", "task_id 不能为空。", field="task_id")
    try:
        task = _task_center_service().get_task(tid)
    except Exception as exc:  # noqa: BLE001
        return _job_tool_error(exc)
    return {"ok": True, "job": _compact_job(task)}


def _legacy_list_jobs(
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


def _legacy_retry_job(
    task_id: str,
    confirmed: bool = False,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
    trace_id: str | None = None,
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
            context=_task_action_context(source, session_id, operator, confirmed=True, trace_id=trace_id),
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


def _legacy_cancel_job(
    task_id: str,
    confirmed: bool = False,
    source: str = "physics_vault_mcp",
    session_id: str | None = None,
    operator: str = "MCP user",
    trace_id: str | None = None,
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
            context=_task_action_context(source, session_id, operator, confirmed=True, trace_id=trace_id),
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
    trace_id: str | None = None,
) -> TaskActionContext:
    return build_task_action_context(source, session_id, operator, confirmed=confirmed, trace_id=trace_id)


def _compact_job(task: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: _mcp_scalar(task.get(key))
        for key in (
            "task_id",
            "trace_id",
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
    include_answers: bool | None,
    include_analysis: bool | None,
    file_name: str | None,
    context: TaskActionContext,
    template_id: str | None = None,
    format_spec: dict[str, Any] | None = None,
    answer_position: str | None = None,
) -> dict[str, Any]:
    if not isinstance(lesson_package, dict) or not str(lesson_package.get("id") or "").strip():
        return _tool_error("INVALID_ARGUMENT", "lesson_package.id 不能为空。", field="lesson_package.id")
    if export_format == "word":
        existing_spec = lesson_package.get("formatSpec") if isinstance(lesson_package.get("formatSpec"), dict) else None
        resolved_spec = format_spec_for_template(template_id, format_spec if format_spec is not None else (None if template_id else existing_spec))
        checked = validate_format_spec(resolved_spec)
        if not checked["ok"]:
            return checked
        lesson_package = {
            **lesson_package,
            "formatSpec": checked["formatSpec"],
            "styleConfig": checked["formatSpec"].get("styleConfig") or lesson_package.get("styleConfig") or {},
            "headerFooter": checked["formatSpec"].get("headerFooter") or lesson_package.get("headerFooter") or {},
        }
        output = checked["formatSpec"].get("output") or {}
        include_answers = bool(output.get("includeAnswers")) if include_answers is None else include_answers
        include_analysis = bool(output.get("includeAnalysis")) if include_analysis is None else include_analysis
        answer_position = answer_position or str(output.get("answerPosition") or "after_question")
    else:
        include_answers = bool(include_answers)
        include_analysis = bool(include_analysis)
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
            answer_position=answer_position or "after_question",
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
_REVIEW_SPLIT_MATH_OPERATOR_RE = re.compile(r"(\$[^$\n]*\s)\$(?=\s*[<>=])")
_REVIEW_TRAILING_ESCAPED_DOLLAR_RE = re.compile(r"\\\$(?=\s*$)")


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
        cleaned, trailing_count = _REVIEW_TRAILING_ESCAPED_DOLLAR_RE.subn("", cleaned)
        cleaned, split_count = _REVIEW_SPLIT_MATH_OPERATOR_RE.subn(r"\1", cleaned)
        cleaned = _REVIEW_MATH_ITALIC_RE.sub(replace, cleaned)
        cleaned, delimiter_count = normalize_math_delimiters(cleaned)
        cleaned, inline_count = repair_unbalanced_inline_math(cleaned)
        standardized = normalize_standard_latex(cleaned)
        standard_count = int(standardized != cleaned)
        return standardized, count + table_count + trailing_count + split_count + delimiter_count + inline_count + standard_count
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
    expected_updated_at: str | None = None,
) -> None:
    with _connect_review_db() as conn:
        # 读取并整体写回 JSON 草稿必须在同一个写事务内，避免自动保存与 MCP 修改互相覆盖。
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT result_json, updated_at FROM import_pipeline_tasks WHERE task_id = ?",
            (str(task_id).strip(),),
        ).fetchone()
        if row is None:
            raise ValueError("校对任务不存在。")
        current_updated_at = str(row["updated_at"] or "")
        expected = str(expected_updated_at or "").strip()
        if expected and expected != current_updated_at:
            raise ReviewTaskConflictError(str(task_id).strip(), expected, current_updated_at)
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


def _review_question_summary(item: Any, index: int, risk_count: int | None = None) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"index": index, "raw_preview": _preview_text(item)}
    question_id = str(item.get("question_id") or item.get("id") or item.get("draft_id") or "").strip()
    title = str(item.get("title") or item.get("canonical_title") or item.get("stem") or "").strip()
    stem = str(item.get("stem") or item.get("stem_text") or item.get("content") or "").strip()
    tags = item.get("tags") or item.get("tag_names") or []
    knowledge = item.get("knowledge_points") or item.get("knowledge_point") or item.get("module") or ""
    risks = item.get("risks") or item.get("warnings") or item.get("validation_warnings") or []
    risk_list = risks if isinstance(risks, list) else [str(risks)]
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
        "risk_count": len(risk_list) if risk_count is None else risk_count,
        "risks": risk_list,
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


_MCP101_LEGACY_HANDLERS = {
    spec.name: globals()[f"_legacy_{spec.name}"]
    for spec in _TOOL_REGISTRY.discover(domain="search")
}
_SEARCH_KNOWLEDGE_DOMAIN = SearchKnowledgeDomain(_MCP101_LEGACY_HANDLERS)
for _mcp101_tool_name in _MCP101_LEGACY_HANDLERS:
    globals()[_mcp101_tool_name] = getattr(_SEARCH_KNOWLEDGE_DOMAIN, _mcp101_tool_name)

_MCP101_TOOL_NAMES = register_search_knowledge_tools(
    server.tool,
    _TOOL_REGISTRY,
    {name: getattr(_SEARCH_KNOWLEDGE_DOMAIN, name) for name in _MCP101_LEGACY_HANDLERS},
)

_MCP102_LEGACY_HANDLERS = {
    spec.name: globals()[f"_legacy_{spec.name}"]
    for spec in _TOOL_REGISTRY.discover(domain="import_review")
}
_IMPORT_REVIEW_DOMAIN = ImportReviewDomain(_MCP102_LEGACY_HANDLERS)
for _mcp102_tool_name in _MCP102_LEGACY_HANDLERS:
    globals()[_mcp102_tool_name] = getattr(_IMPORT_REVIEW_DOMAIN, _mcp102_tool_name)

_MCP102_TOOL_NAMES = register_import_review_tools(
    server.tool,
    _TOOL_REGISTRY,
    {name: getattr(_IMPORT_REVIEW_DOMAIN, name) for name in _MCP102_LEGACY_HANDLERS},
)


_MCP103_LEGACY_HANDLERS = {
    spec.name: globals()[f"_legacy_{spec.name}"]
    for spec in _TOOL_REGISTRY.discover(domain="authoring")
}
_AUTHORING_DOMAIN = AuthoringDomain(_MCP103_LEGACY_HANDLERS)
for _mcp103_tool_name in _MCP103_LEGACY_HANDLERS:
    globals()[_mcp103_tool_name] = getattr(_AUTHORING_DOMAIN, _mcp103_tool_name)

_MCP103_TOOL_NAMES = register_authoring_tools(
    server.tool,
    _TOOL_REGISTRY,
    {name: getattr(_AUTHORING_DOMAIN, name) for name in _MCP103_LEGACY_HANDLERS},
)


_MCP104_LEGACY_HANDLERS = {
    spec.name: globals()[f"_legacy_{spec.name}"]
    for spec in _TOOL_REGISTRY.discover(domain="operations")
}
_OPERATIONS_DOMAIN = OperationsDomain(_MCP104_LEGACY_HANDLERS)
for _mcp104_tool_name in _MCP104_LEGACY_HANDLERS:
    globals()[_mcp104_tool_name] = getattr(_OPERATIONS_DOMAIN, _mcp104_tool_name)

_MCP104_TOOL_NAMES = register_operations_tools(
    server.tool,
    _TOOL_REGISTRY,
    {name: getattr(_OPERATIONS_DOMAIN, name) for name in _MCP104_LEGACY_HANDLERS},
)


_MCP105_LEGACY_HANDLERS = {
    spec.name: globals()[f"_legacy_{spec.name}"]
    for spec in _TOOL_REGISTRY.discover(domain="management")
}
_MANAGEMENT_DOMAIN = ManagementDomain(_MCP105_LEGACY_HANDLERS)
for _mcp105_tool_name in _MCP105_LEGACY_HANDLERS:
    globals()[_mcp105_tool_name] = getattr(_MANAGEMENT_DOMAIN, _mcp105_tool_name)

_MCP105_TOOL_NAMES = register_management_tools(
    server.tool,
    _TOOL_REGISTRY,
    {name: getattr(_MANAGEMENT_DOMAIN, name) for name in _MCP105_LEGACY_HANDLERS},
)


if __name__ == "__main__":
    _validate_tool_registry()
    server.run("stdio")
