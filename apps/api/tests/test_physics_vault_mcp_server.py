import importlib.util
import sqlite3
import sys
import types
from pathlib import Path


def _load_mcp_server():
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    mcpserver_module = types.ModuleType("mcp.server.mcpserver")

    class FakeMCPServer:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.tools = []

        def tool(self):
            def decorator(func):
                self.tools.append(func)
                return func

            return decorator

        def run(self, *args, **kwargs):
            return None

    mcpserver_module.MCPServer = FakeMCPServer
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = server_module
    sys.modules["mcp.server.mcpserver"] = mcpserver_module

    root = Path(__file__).resolve().parents[3]
    module_path = root / "scripts" / "physics_vault_mcp_server.py"
    spec = importlib.util.spec_from_file_location("physics_vault_mcp_server_for_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPECTED_MCP_TOOLS = {
    "list_filter_facets",
    "search_questions",
    "get_questions_by_ids",
    "list_composition_workbenches",
    "get_composition_workbench",
    "create_composition_workbench",
    "add_questions_to_composition_workbench",
    "add_knowledge_to_composition_workbench",
    "insert_teaching_block_to_composition_workbench",
    "reorder_composition_workbench",
    "apply_composition_workbench_plan",
    "curate_questions_to_composition_workbench",
    "list_knowledge_tree",
    "search_knowledge_points",
    "get_question_knowledge_points",
    "create_knowledge_points",
    "batch_update_question_metadata",
    "database_boundary_report",
    "database_health_report",
    "list_review_queue",
    "import_word_folder_to_review",
    "list_review_tasks",
    "get_review_task",
    "get_review_task_full",
    "find_duplicate_review_tasks",
    "delete_review_tasks",
    "suggest_knowledge_points_for_task",
    "clean_review_task_latex",
    "update_review_task_draft",
    "list_question_tags",
    "list_change_batches",
    "get_change_batch",
    "rollback_change_batch",
    "batch_replace_question_tags",
    "return_question_to_review",
    "batch_replace_question_knowledge_points",
    "find_similar_questions",
    "submit_ai_generated_review",
    "submit_import_job",
    "submit_ai_clean_job",
    "submit_word_export_job",
    "submit_pptx_export_job",
    "get_job_status",
    "list_jobs",
    "retry_job",
    "cancel_job",
}


def test_mcp_tool_inventory_is_explicit_and_unique() -> None:
    module = _load_mcp_server()
    names = [tool.__name__ for tool in module.server.tools]

    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_MCP_TOOLS


def test_mcp_latex_cleanup_does_not_truncate_display_math() -> None:
    module = _load_mcp_server()
    raw = {
        "title": "能量关系为 $$E=mc^{2}$$。",
        "analysis": "$$E=6.6 \\times 10^{-34}\\text{ J}$",
    }

    cleaned, replacements = module._clean_latex_value(raw)

    assert cleaned["title"] == "能量关系为 $E=mc^{2}$。"
    assert cleaned["analysis"] == "$$E=6.6 \\times 10^{-34}\\text{ J}$$"
    assert replacements == 2


def test_mcp_argument_errors_use_stable_shape(monkeypatch) -> None:
    module = _load_mcp_server()

    empty_ids = module.get_questions_by_ids([])
    too_many_ids = module.get_questions_by_ids([f"q-{index}" for index in range(51)])
    empty_keyword = module.search_knowledge_points("  ")

    for result in (empty_ids, too_many_ids, empty_keyword):
        assert result["ok"] is False
        assert isinstance(result["error"], str)
        assert result["error_info"]["code"]
        assert result["error_info"]["retryable"] is False

    class MissingDraftService:
        def get(self, draft_id):
            raise ValueError(draft_id)

    monkeypatch.setattr(module, "_paper_draft_service", lambda: MissingDraftService())
    missing = module.get_composition_workbench("missing-draft")
    assert missing["error_info"]["code"] == "DRAFT_NOT_FOUND"
    assert missing["draft_id"] == "missing-draft"


def test_word_folder_filter_and_duplicate_preview(tmp_path, monkeypatch) -> None:
    module = _load_mcp_server()
    (tmp_path / "2026浙江卷.docx").write_bytes(b"same word content")
    (tmp_path / "2026广东卷.docx").write_bytes(b"other word content")

    class ImportService:
        def find_import_batches_by_sha256(self, digest):
            return [{"batch_id": "batch-old", "status": "completed"}]

    monkeypatch.setattr(module, "_import_service", lambda: ImportService())

    preview = module.import_word_folder_to_review(
        str(tmp_path),
        file_filter="*浙江*",
        skip_if_duplicate=True,
    )
    reimport = module.import_word_folder_to_review(
        str(tmp_path),
        file_filter="*浙江*",
        skip_if_duplicate=False,
    )

    assert preview["file_count"] == 0
    assert preview["duplicates"][0]["action"] == "skipped"
    assert reimport["file_count"] == 1
    assert reimport["duplicates"][0]["action"] == "reimport"


def _seed_standard_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE questions (
                question_id TEXT PRIMARY KEY,
                canonical_title TEXT,
                question_type TEXT,
                difficulty INTEGER,
                module TEXT,
                topic2 TEXT,
                topic3 TEXT,
                status TEXT DEFAULT 'approved',
                review_status TEXT DEFAULT 'confirmed',
                review_comment TEXT,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE question_text_index (
                question_id TEXT PRIMARY KEY,
                title_text TEXT,
                stem_text TEXT NOT NULL DEFAULT '',
                options_json TEXT NOT NULL DEFAULT '[]',
                sub_questions_json TEXT NOT NULL DEFAULT '[]',
                figures_json TEXT NOT NULL DEFAULT '[]',
                image_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                image_filenames_json TEXT NOT NULL DEFAULT '[]',
                image_count INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL DEFAULT '[]',
                source_text TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE knowledge_points (
                topic3_id TEXT PRIMARY KEY,
                topic3_name TEXT NOT NULL,
                topic2_id TEXT NOT NULL,
                topic2_name TEXT NOT NULL,
                topic1_id TEXT NOT NULL,
                topic1_name TEXT NOT NULL,
                source_chapter TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            );
            CREATE TABLE question_knowledge_points (
                link_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                topic3_id TEXT NOT NULL,
                rank INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'manual',
                confidence REAL NOT NULL DEFAULT 1.0,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE question_search_fts (question_id TEXT PRIMARY KEY);
            CREATE TABLE question_sources (source_id TEXT PRIMARY KEY, question_id TEXT);
            CREATE TABLE question_versions (version_id TEXT PRIMARY KEY, question_id TEXT);
            INSERT INTO questions (question_id, canonical_title, question_type, difficulty, module, source)
            VALUES ('q-001', 'Newton second law', 'single_choice', 1, 'mechanics', 'unit');
            INSERT INTO question_text_index (question_id, title_text, stem_text, tags_json)
            VALUES ('q-001', 'Newton second law', 'A force acts on a cart.', '["mechanics", "basic", "mechanics"]');
            INSERT INTO knowledge_points (
                topic3_id, topic3_name, topic2_id, topic2_name, topic1_id, topic1_name, source_chapter, status
            ) VALUES (
                'KP-MECH-DYN-NEWTON2', 'Newton second law', 'KP-MECH-DYN', 'Dynamics',
                'KP-MECH', 'Mechanics', 'required', 'active'
            );
            """
        )


def _seed_review_db(module, path: Path) -> None:
    with sqlite3.connect(path) as conn:
        module._ensure_review_db_schema(conn)
        conn.execute(
            """
            INSERT INTO import_pipeline_tasks (
                task_id, task_type, status, created_at, updated_at, input_summary_json, result_json, error
            ) VALUES (
                'task-review-001', 'ai_generated_review', 'completed',
                '2026-07-29T00:00:00+00:00', '2026-07-29T00:01:00+00:00',
                '{"source":"AI review"}',
                '{"batch_id":"batch-001","source":"AI review","question_count":1,"knowledge_count":0,"questions":[{"question_id":"draft-001","title":"Newton draft","stem":"A force acts on a cart.","answer":"B","tags":["mechanics","mechanics"],"status":"pending"}],"warnings":["needs answer check"]}',
                NULL
            )
            """
        )


def _configure_paths(module, tmp_path: Path, monkeypatch):
    standard_db = tmp_path / "physics_vault.sqlite3"
    review_db = tmp_path / "review_workspace.sqlite3"
    _seed_standard_db(standard_db)
    monkeypatch.setattr(module, "default_db_path", lambda: standard_db)
    monkeypatch.setattr(module, "default_review_db_path", lambda: review_db)
    _seed_review_db(module, review_db)
    return standard_db, review_db


def test_tag_normalization_is_dry_run_first_and_audited(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)

    inventory = module.list_question_tags(question_ids=["q-001"])
    assert inventory["items"][0]["tags"] == ["mechanics", "basic"]

    preview = module.batch_replace_question_tags(
        [{"question_id": "q-001", "tags": ["mechanics", "newton_laws"]}],
    )
    assert preview["dry_run"] is True
    assert preview["changed_count"] == 1
    assert preview["requires_confirmation"] is True

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT tags_json FROM question_text_index WHERE question_id='q-001'").fetchone()[0] == '["mechanics", "basic", "mechanics"]'

    applied = module.batch_replace_question_tags(
        [{"question_id": "q-001", "tags": ["mechanics", "newton_laws"]}],
        dry_run=False,
        reason="tighten tags",
    )
    assert applied["dry_run"] is False
    assert applied["audit_batch_id"]

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT tags_json FROM question_text_index WHERE question_id='q-001'").fetchone()[0] == '["mechanics", "newton_laws"]'
        assert conn.execute(
            "SELECT change_type FROM change_batches WHERE batch_id = ?",
            (applied["audit_batch_id"],),
        ).fetchone()[0] == "tag_normalization"

    batch = module.get_change_batch(applied["audit_batch_id"])
    assert batch["ok"] is True
    assert batch["items"][0]["before_value"] == ["mechanics", "basic"]

    rollback_preview = module.rollback_change_batch(applied["audit_batch_id"])
    assert rollback_preview["dry_run"] is True
    assert rollback_preview["changed_count"] == 1
    assert rollback_preview["items"][0]["status"] == "will_rollback"

    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo tag normalization",
    )
    assert rollback["ok"] is True
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT tags_json FROM question_text_index WHERE question_id='q-001'").fetchone()[0] == '["mechanics", "basic"]'
        assert conn.execute("SELECT status FROM change_batches WHERE batch_id = ?", (applied["audit_batch_id"],)).fetchone()[0] == "rolled_back"


def test_return_to_review_updates_canonical_status_but_writes_queue_to_review_db(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)

    preview = module.return_question_to_review("q-001", reason="needs rework")
    assert preview["dry_run"] is True
    assert preview["item"]["after_status"] == "待校对"

    applied = module.return_question_to_review("q-001", reason="needs rework", dry_run=False)
    assert applied["dry_run"] is False
    assert applied["audit_batch_id"]

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT status, review_status FROM questions WHERE question_id='q-001'").fetchone() == ("待校对", "reviewing")
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='review_queue'").fetchone() is None

    with sqlite3.connect(review_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 1

    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo return to review",
    )
    assert rollback["ok"] is True
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT status, review_status FROM questions WHERE question_id='q-001'").fetchone() == ("approved", "confirmed")
    with sqlite3.connect(review_db) as conn:
        assert conn.execute("SELECT status FROM review_queue WHERE entity_id='q-001'").fetchone()[0] == "rolled_back"


def test_knowledge_binding_normalization_is_audited(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)

    preview = module.batch_replace_question_knowledge_points(
        [{"question_id": "q-001", "topic3_ids": ["KP-MECH-DYN-NEWTON2"]}],
    )
    assert preview["dry_run"] is True
    assert preview["changed_count"] == 1

    applied = module.batch_replace_question_knowledge_points(
        [{"question_id": "q-001", "topic3_ids": ["KP-MECH-DYN-NEWTON2"]}],
        dry_run=False,
        reason="bind directory",
    )
    assert applied["dry_run"] is False
    assert applied["audit_batch_id"]

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT topic3_id FROM question_knowledge_points WHERE question_id='q-001'").fetchone()[0] == "KP-MECH-DYN-NEWTON2"
        assert conn.execute(
            "SELECT change_type FROM change_batches WHERE batch_id = ?",
            (applied["audit_batch_id"],),
        ).fetchone()[0] == "knowledge_binding_normalization"

    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo knowledge binding",
    )
    assert rollback["ok"] is True
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM question_knowledge_points WHERE question_id='q-001'").fetchone()[0] == 0


def test_rollback_blocks_current_value_conflicts(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)
    applied = module.batch_replace_question_tags(
        [{"question_id": "q-001", "tags": ["mechanics", "newton_laws"]}],
        dry_run=False,
        reason="tighten tags",
    )
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "UPDATE question_text_index SET tags_json = ? WHERE question_id = 'q-001'",
            ('["later_change"]',),
        )

    preview = module.rollback_change_batch(applied["audit_batch_id"])
    assert preview["conflict_count"] == 1
    assert preview["items"][0]["status"] == "current_value_conflict"

    blocked = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="try rollback",
    )
    assert blocked["ok"] is False


def test_review_tools_use_review_db_with_legacy_task_migration(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)

    tasks = module.list_review_tasks()
    assert tasks["total"] == 1
    assert tasks["items"][0]["task_id"] == "task-review-001"

    full = module.get_review_task_full("task-review-001")
    assert full["ok"] is True
    assert full["questions"][0]["stem"] == "A force acts on a cart."

    applied = module.update_review_task_draft(
        "task-review-001",
        [{"question_id": "draft-001", "stem": "A force acts on a cart with mass m."}],
        dry_run=False,
        reason="fix draft wording",
    )
    assert applied["dry_run"] is False

    with sqlite3.connect(review_db) as conn:
        saved = conn.execute("SELECT result_json FROM import_pipeline_tasks WHERE task_id='task-review-001'").fetchone()[0]
    assert "mass m" in saved

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='import_pipeline_tasks'").fetchone() is None


def test_review_queue_is_read_from_review_db_and_enriched_from_canonical_db(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    with sqlite3.connect(review_db) as conn:
        module._ensure_review_db_schema(conn)
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status, priority, reason, payload_json
            ) VALUES (
                'rev-001', 'question', 'q-001', 'rework', 'pending', 5, 'needs cleanup',
                '{"source":"test"}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO review_queue (
                review_id, entity_type, entity_id, queue_type, status, priority, reason, payload_json
            ) VALUES (
                'rev-orphan', 'question', 'q-missing', 'manual', 'pending', 6, 'demo residue',
                '{"source":"test"}'
            )
            """
        )

    queue = module.list_review_queue()
    assert queue["total"] == 1
    assert queue["orphan_count"] == 1
    assert queue["items"][0]["question"]["tags"] == ["mechanics", "basic"]

    unfiltered = module.list_review_queue(include_orphans=True)
    assert unfiltered["total"] == 2


def test_search_questions_blocks_review_intent_misroute(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)

    result = module.search_questions(query="帮我处理送审的15道草稿题")

    assert result["misrouted"] is True
    assert result["requested_scope"] == "review_workspace"
    assert result["next_tools"][0] == "list_review_tasks"


def test_database_boundary_report_separates_canonical_and_review_databases(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)

    report = module.database_boundary_report()

    assert report["ok"] is True
    assert report["database_boundary"]["canonical_database"]["path"] == str(standard_db)
    assert report["database_boundary"]["review_database"]["path"] == str(review_db)
    assert report["database_boundary"]["same_file"] is False
    assert "list_review_tasks" in report["routing"]["review_center_first"]
    assert report["next_tool_when_user_says_submitted_or_review"] == "list_review_tasks"


def test_job_mutations_require_confirmation_and_return_compact_audited_results(monkeypatch):
    module = _load_mcp_server()

    class FakeTaskCenter:
        def __init__(self):
            self.retry_calls = []
            self.cancel_calls = []

        def get_task(self, task_id):
            return {
                "task_id": task_id,
                "task_type": "background_recognize",
                "task_name": "导入识别",
                "status": "failed",
                "progress": 40,
                "current_step": "recognize",
                "input_summary": {"large": "x" * 10_000},
                "result_available": False,
            }

        def retry_job(self, task_id, *, context):
            self.retry_calls.append((task_id, context))
            task = self.get_task("new-task")
            task["status"] = "pending"
            return task, task_id, "audit-retry"

        def cancel_job(self, task_id, *, context):
            self.cancel_calls.append((task_id, context))
            task = self.get_task(task_id)
            task["status"] = "cancel_requested"
            return task, "audit-cancel"

    service = FakeTaskCenter()
    monkeypatch.setattr(module, "_task_center_service", lambda: service)

    preview = module.retry_job("task-001")
    assert preview["confirmation_required"] is True
    assert service.retry_calls == []
    assert "input_summary" not in preview["job"]

    retried = module.retry_job(
        "task-001",
        confirmed=True,
        session_id="session-001",
        operator="teacher-001",
    )
    assert retried["ok"] is True
    assert retried["audit_id"] == "audit-retry"
    assert service.retry_calls[0][1].confirmed is True
    assert service.retry_calls[0][1].session_id == "session-001"

    cancel_preview = module.cancel_job("task-002")
    assert cancel_preview["confirmation_required"] is True
    assert service.cancel_calls == []

    cancelled = module.cancel_job("task-002", confirmed=True)
    assert cancelled["job"]["status"] == "cancel_requested"
    assert cancelled["audit_id"] == "audit-cancel"


def test_export_job_tools_fail_closed_when_server_export_service_is_missing(monkeypatch):
    module = _load_mcp_server()
    monkeypatch.setattr(module, "_task_center_service", lambda: object())

    result = module.submit_word_export_job({"id": "lesson-001", "questions": [], "nodes": []})

    assert result["ok"] is False
    assert result["capability_unavailable"] is True
    assert "未创建任务" in result["message"]


def test_export_job_tool_calls_formal_service_without_echoing_snapshot(monkeypatch):
    module = _load_mcp_server()

    class FakeTaskCenter:
        def submit_export_job(self, export_format, lesson_package, **kwargs):
            assert export_format == "pptx"
            assert lesson_package["id"] == "lesson-002"
            assert kwargs["context"].session_id == "session-pptx"
            return (
                {
                    "task_id": "export-002",
                    "task_type": "pptx_export",
                    "task_name": "PPTX 导出",
                    "status": "completed",
                    "progress": 100,
                    "result_available": True,
                    "result_summary": {"filename": "lesson.pptx", "export_format": "pptx"},
                    "input_summary": {"lesson_package": lesson_package},
                },
                "audit-export",
            )

    monkeypatch.setattr(module, "_task_center_service", lambda: FakeTaskCenter())
    result = module.submit_pptx_export_job(
        {"id": "lesson-002", "questions": [{"stem": "large snapshot"}], "nodes": []},
        session_id="session-pptx",
    )

    assert result["ok"] is True
    assert result["audit_id"] == "audit-export"
    assert result["job"]["download_url"] == "/api/tasks/export-002/download"
    assert "input_summary" not in result["job"]
