import importlib.util
import inspect
import json
import sqlite3
import sys
import types
from copy import deepcopy
from contextlib import nullcontext
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
    "get_workflow_guide",
    "mcp_system_health",
    "list_teaching_projects",
    "get_teaching_project",
    "get_teaching_project_status",
    "duplicate_teaching_project",
    "publish_teaching_artifact",
    "preflight_teaching_handout",
    "sync_teaching_slides",
    "start_classroom_session",
    "get_classroom_session",
    "update_classroom_session",
    "end_classroom_session",
    "list_filter_facets",
    "search_questions",
    "search_questions_compact",
    "search_questions_curated",
    "search_method_questions",
    "record_method_retrieval_feedback",
    "list_method_retrieval_feedback",
    "method_retrieval_learning_report",
    "search_topic_questions",
    "get_questions_by_ids",
    "export_questions_to_typst",
    "download_question_images",
    "scan_canonical_duplicate_questions",
    "backfill_canonical_question_hashes",
    "merge_canonical_duplicate_questions",
    "restore_canonical_duplicate_merge",
    "list_canonical_duplicate_merges",
    "list_composition_workbenches",
    "get_composition_workbench",
    "create_composition_workbench",
    "add_questions_to_composition_workbench",
    "add_knowledge_to_composition_workbench",
    "insert_teaching_block_to_composition_workbench",
    "reorder_composition_workbench",
    "move_composition_item",
    "remove_items_from_composition_workbench",
    "update_composition_item",
    "lock_composition_workbench",
    "apply_composition_workbench_plan",
    "preview_composition_workbench",
    "export_composition_workbench",
    "list_word_export_templates",
    "get_word_export_template",
    "propose_word_export_format",
    "validate_word_export_format",
    "save_word_export_template",
    "rename_word_export_template",
    "list_saved_handouts",
    "get_saved_handout",
    "list_saved_handout_versions",
    "restore_saved_handout_version",
    "rename_saved_handout",
    "apply_word_format_to_saved_handout",
    "apply_word_format_to_workbench",
    "export_saved_handout",
    "curate_questions_to_composition_workbench",
    "list_knowledge_tree",
    "search_knowledge_points",
    "get_question_knowledge_points",
    "maintain_question_knowledge_points",
    "diagnose_tag_maintenance",
    "suggest_question_tags",
    "maintain_question_tags",
    "create_knowledge_points",
    "associate_questions_to_paper",
    "create_paper",
    "organize_knowledge_tree",
    "batch_update_question_metadata",
    "database_boundary_report",
    "database_health_report",
    "list_review_queue",
    "import_word_folder_to_review",
    "list_review_tasks",
    "get_review_task",
    "get_review_task_full",
    "validate_review_task",
    "split_merged_options",
    "deduplicate_review_task_questions",
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
    "reconcile_review_queue_outbox",
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


def test_workflow_guide_routes_common_intents() -> None:
    module = _load_mcp_server()

    result = module.get_workflow_guide("我要组卷并调整题目顺序")

    assert result["matched_count"] == 1
    assert result["workflows"][0]["id"] == "composition"
    assert result["workflows"][0]["start_tool"] == "search_questions_curated"
    assert "apply_composition_workbench_plan" in result["workflows"][0]["tools"]


def test_mcp_tool_inventory_is_explicit_and_unique() -> None:
    module = _load_mcp_server()
    names = [tool.__name__ for tool in module.server.tools]

    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_MCP_TOOLS


def test_publish_plan_token_is_version_bound_and_idempotent(tmp_path, monkeypatch) -> None:
    module = _load_mcp_server()
    service = module.OperationPlanService(module.OperationPlanRepository(tmp_path / "plans.sqlite3"))
    monkeypatch.setattr(module, "_mcp_operation_plan_service", lambda: service)
    state = {
        "id": "project-1",
        "updatedAt": "2026-08-12T00:00:00+00:00",
        "contentRevision": 3,
        "slides": {
            "status": "ready",
            "sourceRevision": 3,
            "publishedSnapshot": {"version": 1, "lessonPackage": {"id": "lesson-1"}},
        },
    }
    saves = []

    monkeypatch.setattr(module, "_get_teaching_project", lambda project_id: deepcopy(state) if project_id == "project-1" else None)

    def save(project, *, base_updated_at=None):
        assert base_updated_at == state["updatedAt"]
        saves.append(deepcopy(project))
        state.clear()
        state.update(deepcopy(project))
        state["updatedAt"] = f"saved-{len(saves)}"
        return deepcopy(state)

    monkeypatch.setattr(module, "_save_teaching_project", save)

    preview = module.publish_teaching_artifact("project-1")
    assert preview["dry_run"] is True
    assert preview["plan_token"] == preview["operation_plan"]["operation_id"]

    missing = module.publish_teaching_artifact("project-1", confirmed=True)
    assert missing["error_info"]["code"] == "PLAN_TOKEN_REQUIRED"

    executed = module.publish_teaching_artifact("project-1", confirmed=True, plan_token=preview["plan_token"])
    assert executed["ok"] is True
    assert executed["published_version"] == 2
    assert executed["idempotent"] is False

    replay = module.publish_teaching_artifact("project-1", confirmed=True, plan_token=preview["plan_token"])
    assert replay["idempotent"] is True
    assert len(saves) == 1

    stale_preview = module.publish_teaching_artifact("project-1")
    state["updatedAt"] = "changed-after-preview"
    conflict = module.publish_teaching_artifact("project-1", confirmed=True, plan_token=stale_preview["plan_token"])
    assert conflict["error_info"]["code"] == "OPERATION_PLAN_VERSION_CONFLICT"
    assert len(saves) == 1


def test_saved_handout_format_plan_is_version_bound_and_idempotent(tmp_path, monkeypatch) -> None:
    module = _load_mcp_server()
    service = module.OperationPlanService(module.OperationPlanRepository(tmp_path / "plans.sqlite3"))
    monkeypatch.setattr(module, "_mcp_operation_plan_service", lambda: service)
    state = {
        "id": "handout-1",
        "title": "力学讲义",
        "currentVersion": 1,
        "updatedAt": "2026-08-12T00:00:00+00:00",
        "lessonPackage": {"formatSpec": {"styleConfig": {"fontSize": 10}}},
    }
    writes = []

    monkeypatch.setattr(
        module,
        "_get_saved_handout_store",
        lambda document_id: deepcopy(state) if document_id == "handout-1" else None,
    )
    monkeypatch.setattr(module, "format_spec_for_template", lambda _template_id, spec: deepcopy(spec or {}))
    monkeypatch.setattr(
        module,
        "validate_format_spec",
        lambda spec: {"ok": True, "formatSpec": deepcopy(spec)},
    )

    def update(document_id, format_spec, *, template_id=None):
        assert document_id == "handout-1"
        writes.append({"format_spec": deepcopy(format_spec), "template_id": template_id})
        state["currentVersion"] += 1
        state["updatedAt"] = f"saved-{len(writes)}"
        state["formatTemplateId"] = template_id
        state["lessonPackage"]["formatSpec"] = deepcopy(format_spec)
        return deepcopy(state)

    monkeypatch.setattr(module, "_update_saved_handout_format_store", update)
    target = {"styleConfig": {"fontSize": 12}}

    preview = module.apply_word_format_to_saved_handout(
        "handout-1", template_id="teacher", format_spec=target
    )
    assert preview["dry_run"] is True
    assert preview["plan_token"] == preview["operation_plan"]["operation_id"]

    missing = module.apply_word_format_to_saved_handout(
        "handout-1", template_id="teacher", format_spec=target, dry_run=False
    )
    assert missing["error_info"]["code"] == "PLAN_TOKEN_REQUIRED"

    executed = module.apply_word_format_to_saved_handout(
        "handout-1",
        template_id="teacher",
        format_spec=target,
        dry_run=False,
        plan_token=preview["plan_token"],
    )
    assert executed["ok"] is True
    assert executed["idempotent"] is False
    assert len(writes) == 1

    replay = module.apply_word_format_to_saved_handout(
        "handout-1",
        template_id="teacher",
        format_spec=target,
        dry_run=False,
        plan_token=preview["plan_token"],
    )
    assert replay["idempotent"] is True
    assert len(writes) == 1

    stale_preview = module.apply_word_format_to_saved_handout(
        "handout-1", template_id="student", format_spec=target
    )
    state["updatedAt"] = "changed-after-preview"
    conflict = module.apply_word_format_to_saved_handout(
        "handout-1",
        template_id="student",
        format_spec=target,
        dry_run=False,
        plan_token=stale_preview["plan_token"],
    )
    assert conflict["error_info"]["code"] == "OPERATION_PLAN_VERSION_CONFLICT"
    assert len(writes) == 1


def test_catalog_profile_exposes_only_catalog_tools(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_MCP_PROFILE", "catalog")
    module = _load_mcp_server()
    names = {tool.__name__ for tool in module.server.tools}

    assert "search_questions" in names
    assert "scan_canonical_duplicate_questions" in names
    assert "merge_canonical_duplicate_questions" not in names
    assert "list_review_tasks" not in names
    assert "apply_composition_workbench_plan" not in names


def test_authoring_profile_and_public_legacy_signatures_are_compatible(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_MCP_PROFILE", "authoring")
    module = _load_mcp_server()
    authoring_names = tuple(module._MCP103_TOOL_NAMES)

    assert set(authoring_names) == module.profile_tool_names("authoring")
    assert {tool.__name__ for tool in module.server.tools} == set(authoring_names)
    for name in authoring_names:
        assert inspect.signature(getattr(module, name)) == inspect.signature(
            getattr(module, f"_legacy_{name}")
        )


def test_operations_profile_and_public_legacy_signatures_are_compatible(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_MCP_PROFILE", "operations")
    module = _load_mcp_server()
    operation_names = tuple(module._MCP104_TOOL_NAMES)

    assert set(operation_names) == module.profile_tool_names("operations")
    assert {tool.__name__ for tool in module.server.tools} == set(operation_names)
    for name in operation_names:
        assert inspect.signature(getattr(module, name)) == inspect.signature(
            getattr(module, f"_legacy_{name}")
        )


def test_management_profile_and_public_legacy_signatures_are_compatible(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_MCP_PROFILE", "catalog_maintenance")
    module = _load_mcp_server()
    management_names = tuple(module._MCP105_TOOL_NAMES)

    assert set(management_names) == module.profile_tool_names("catalog_maintenance")
    assert {tool.__name__ for tool in module.server.tools} == set(management_names)
    for name in management_names:
        assert inspect.signature(getattr(module, name)) == inspect.signature(
            getattr(module, f"_legacy_{name}")
        )


def test_mcp_format_diff_reports_changed_sections_and_template_ids() -> None:
    module = _load_mcp_server()

    changes = module._format_spec_diff(
        {
            "styleConfig": {"fontSize": 12, "figureScale": 60},
            "output": {"includeAnswers": False},
        },
        {
            "styleConfig": {"fontSize": 14, "figureScale": 60},
            "output": {"includeAnswers": True},
        },
        before_template_id="student_practice",
        after_template_id="teacher_handout",
    )

    assert changes == {
        "changed_sections": ["output", "styleConfig"],
        "changed_fields": {
            "output": ["includeAnswers"],
            "styleConfig": ["fontSize"],
        },
        "before_template_id": "student_practice",
        "after_template_id": "teacher_handout",
    }


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


def test_create_paper_is_idempotent_and_rejects_conflicts(tmp_path, monkeypatch) -> None:
    module = _load_mcp_server()
    db_path = tmp_path / "papers.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY,
                year INTEGER,
                exam_type TEXT,
                region TEXT,
                paper_name TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT 'PHY',
                status TEXT NOT NULL DEFAULT 'structured'
            )
            """
        )
    monkeypatch.setattr(module, "_formal_db_path", lambda: db_path)

    created = module.create_paper("paper-gd-2026", "2026 Guangdong Physics", 2026, "Guangdong", "Gaokao")
    same = module.create_paper("paper-gd-2026", "2026 Guangdong Physics", 2026, "Guangdong", "Gaokao")
    conflict = module.create_paper("paper-gd-2026", "Other paper", 2026, "Guangdong", "Gaokao")

    assert created["ok"] is True and created["created"] is True
    assert same["ok"] is True and same["created"] is False
    assert conflict["ok"] is False
    assert conflict["error_info"]["code"] == "PAPER_CONFLICT"


def test_composition_plan_accepts_rich_workbench_only_knowledge_card(monkeypatch) -> None:
    module = _load_mcp_server()

    class DraftService:
        def __init__(self):
            self.saved = None

        def get(self, draft_id):
            return {
                "id": draft_id,
                "title": "Lesson",
                "source": "compose",
                "status": "draft",
                "items": [],
                "metadata": {},
                "quality_report": {},
                "question_count": 0,
                "item_count": 0,
                "total_score": 0,
                "created_at": "v1",
                "updated_at": "v1",
            }

        def save(self, request):
            self.saved = request
            return {
                "id": request.id,
                "title": request.title,
                "source": request.source,
                "status": request.status,
                "items": request.items,
                "metadata": request.metadata,
                "quality_report": request.quality_report,
                "question_count": 0,
                "item_count": len(request.items),
                "total_score": 0,
                "created_at": "v1",
                "updated_at": "v2",
            }

    service = DraftService()
    monkeypatch.setattr(module, "_paper_draft_service", lambda: service)
    monkeypatch.setattr(module, "_connect_formal_read_db", lambda: nullcontext(None))

    empty = module.apply_composition_workbench_plan(
        draft_id="draft-1",
        dry_run=False,
        operations=[{"ref": "empty", "kind": "knowledge", "title": "Reference frames"}],
    )
    assert empty["ok"] is False
    assert "缺少实际讲解内容" in empty["error"]
    assert service.saved is None

    result = module.apply_composition_workbench_plan(
        draft_id="draft-1",
        dry_run=False,
        operations=[
            {
                "ref": "knowledge-1",
                "kind": "knowledge",
                "title": "Reference frames",
                "content": "Choose a reference object before comparing positions.",
                "points": ["Motion is relative", "Keep one frame throughout"],
                "related_question_ids": ["q-3"],
            }
        ],
    )

    assert result["ok"] is True
    assert service.saved.base_updated_at == "v1"
    payload = service.saved.items[0].payload
    assert payload["topic3_id"] is None
    assert payload["title"] == "Reference frames"
    assert payload["content"] == "Choose a reference object before comparing positions."
    assert payload["summary"].startswith("Choose a reference object")
    assert payload["points"] == ["Motion is relative", "Keep one frame throughout"]
    assert payload["relatedQuestionIds"] == ["q-3"]


def test_composition_plan_replaces_existing_template_knowledge_card(monkeypatch) -> None:
    module = _load_mcp_server()
    topic_id = "KP-MECH-DYN-NEWTON3"
    existing_id = "compose-knowledge-old"

    class DraftService:
        def __init__(self):
            self.saved = None

        def get(self, draft_id):
            return {
                "id": draft_id,
                "title": "Lesson",
                "source": "compose",
                "status": "draft",
                "items": [
                    {
                        "id": "question-1",
                        "type": "question",
                        "position": 0,
                        "question_id": "q-1",
                        "payload": {},
                    },
                    {
                        "id": existing_id,
                        "type": "knowledge",
                        "position": 1,
                        "title": "Old template",
                        "payload": {
                            "id": topic_id,
                            "topic3_id": topic_id,
                            "summary": "力学 / 相互作用",
                            "points": ["概念与条件：旧模板"],
                        },
                    },
                ],
                "metadata": {},
                "quality_report": {},
                "question_count": 1,
                "item_count": 2,
                "total_score": 0,
                "created_at": "v1",
                "updated_at": "v1",
            }

        def save(self, request):
            self.saved = request
            return {
                "id": request.id,
                "title": request.title,
                "source": request.source,
                "status": request.status,
                "items": request.items,
                "metadata": request.metadata,
                "quality_report": request.quality_report,
                "question_count": 1,
                "item_count": len(request.items),
                "total_score": 0,
                "created_at": "v1",
                "updated_at": "v2",
            }

    topic = {
        "topic1_id": "KP-MECH",
        "topic1_name": "力学",
        "topic2_id": "KP-MECH-DYN",
        "topic2_name": "相互作用",
        "topic3_id": topic_id,
        "topic3_name": "牛顿第三定律",
        "source_chapter": "必修一",
    }
    service = DraftService()
    monkeypatch.setattr(module, "_paper_draft_service", lambda: service)
    monkeypatch.setattr(module, "_connect_formal_read_db", lambda: nullcontext(None))
    monkeypatch.setattr(module, "_fetch_topics", lambda _conn, _ids: {topic_id: topic})

    result = module.apply_composition_workbench_plan(
        draft_id="draft-1",
        dry_run=False,
        operations=[{
            "ref": "newton-explanation",
            "kind": "knowledge",
            "topic3_id": topic_id,
            "title": "为什么掰手腕双方受力始终相等",
            "content": "两只手之间的作用力同时产生，大小相等、方向相反。胜负由其他受力和力矩决定。",
            "related_question_ids": ["q-1"],
        }],
    )

    assert result["ok"] is True
    assert result["draft"]["item_count"] == 2
    replacement = service.saved.items[1]
    assert replacement.id == existing_id
    assert replacement.title == "为什么掰手腕双方受力始终相等"
    assert replacement.payload["points"]
    assert replacement.payload["content"].startswith("\u4e24\u53ea")
    assert "同时产生" in replacement.payload["summary"]


def test_composition_item_mutations_support_partial_order_and_rich_updates(monkeypatch) -> None:
    module = _load_mcp_server()

    class DraftService:
        def __init__(self):
            self.current = {
                "id": "draft-1", "title": "Lesson", "source": "compose", "status": "draft",
                "items": [
                    {"id": "a", "type": "text", "title": "A", "payload": {"content": "a"}},
                    {"id": "b", "type": "knowledge", "title": "B", "payload": {"title": "B", "content": "old", "summary": "old", "points": ["old"]}},
                    {"id": "c", "type": "question", "title": "C", "question_id": "q-1", "payload": {}},
                ],
                "metadata": {}, "quality_report": {}, "question_count": 1, "item_count": 3,
                "total_score": 0, "created_at": "v1", "updated_at": "v1",
            }

        def get(self, _draft_id):
            return self.current

        def save(self, request):
            self.current = {**self.current, "items": [item.model_dump() for item in request.items], "metadata": request.metadata, "item_count": len(request.items), "updated_at": "v2"}
            return self.current

    service = DraftService()
    monkeypatch.setattr(module, "_paper_draft_service", lambda: service)

    updated = module.update_composition_item("b", {"title": "B2", "content": "# New explanation"}, draft_id="draft-1", dry_run=False)
    assert updated["ok"] is True
    assert service.current["items"][1]["payload"]["points"] == ["New explanation"]
    assert service.current["items"][1]["payload"]["content"] == "# New explanation"

    moved = module.move_composition_item("b", after_item_id="c", draft_id="draft-1", dry_run=False)
    assert moved["ok"] is True
    assert [item["id"] for item in service.current["items"]] == ["a", "c", "b"]

    removed = module.remove_items_from_composition_workbench(["a"], draft_id="draft-1", dry_run=False)
    assert removed["ok"] is True
    assert [item["id"] for item in service.current["items"]] == ["c", "b"]


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
                content_hash TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE question_text_index (
                question_id TEXT PRIMARY KEY,
                title_text TEXT,
                stem_text TEXT NOT NULL DEFAULT '',
                answer_text TEXT,
                analysis_text TEXT,
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
            CREATE TABLE image_assets (
                asset_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                question_id TEXT
            );
            CREATE TABLE question_assets (
                link_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'question_figure',
                sort_order INTEGER NOT NULL DEFAULT 0,
                placeholder_key TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                is_verified INTEGER NOT NULL DEFAULT 0
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
            CREATE TABLE question_sources (
                source_id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL,
                source_label TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE question_versions (version_id TEXT PRIMARY KEY, question_id TEXT);
            INSERT INTO questions (question_id, canonical_title, question_type, difficulty, module, source)
            VALUES ('q-001', 'Newton second law', 'single_choice', 1, 'mechanics', 'unit');
            INSERT INTO question_text_index (question_id, title_text, stem_text, answer_text, tags_json)
            VALUES ('q-001', 'Newton second law', 'A force acts on a cart.', 'A', '["mechanics", "basic", "mechanics"]');
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


def test_download_question_images_copies_managed_assets_for_agent_use(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "project_root", lambda: tmp_path)
    source = tmp_path / "data" / "assets" / "questions" / "force-diagram.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test-image-bytes")
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "INSERT INTO image_assets (asset_id, filename, file_path, question_id) VALUES (?, ?, ?, ?)",
            ("asset-force", source.name, "data/assets/questions/force-diagram.png", "q-001"),
        )
        conn.execute(
            "INSERT INTO question_assets (link_id, question_id, asset_id, sort_order) VALUES (?, ?, ?, ?)",
            ("qa-force", "q-001", "asset-force", 0),
        )

    downloaded = module.download_question_images("q-001", destination_subdir="agent-run")

    assert downloaded["ok"] is True
    assert downloaded["downloaded_count"] == 1
    image = downloaded["images"][0]
    assert image["status"] == "downloaded"
    assert image["reused_existing_file"] is False
    assert Path(image["local_path"]).read_bytes() == b"test-image-bytes"
    assert Path(image["local_path"]).is_relative_to(tmp_path / "data" / "mcp-downloads")

    reused = module.download_question_images("q-001", destination_subdir="agent-run")
    assert reused["images"][0]["reused_existing_file"] is True
    invalid_destination = module.download_question_images("q-001", destination_subdir="../outside")
    assert invalid_destination["error_info"]["code"] == "INVALID_ARGUMENT"


def test_comprehensive_method_search_uses_structure_analysis_and_source_filters(tmp_path, monkeypatch):
    module = _load_mcp_server()
    expanded_terms = module._comprehensive_query_terms(
        "电磁感应 配速法 洛伦兹力 摆线"
    )
    assert "速度分解" in expanded_terms
    assert "法拉第" not in expanded_terms
    assert "楞次定律" not in expanded_terms

    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, module, topic3, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Q00000298",
                "2008 江苏经典带电小球题",
                "calculation",
                5,
                "mechanics",
                "圆周运动",
                "2008年高考江苏卷物理",
            ),
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, answer_text, analysis_text, tags_json, source_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Q00000298",
                "带电小球在水平磁场中运动",
                "水平匀强磁场中，带正电小球从O点静止释放，求运动曲线最低点和最大下降距离。重力加速度为g。",
                "略",
                "洛伦兹力不做功，由动能定理和最低点曲率半径求解。",
                "[]",
                "2008年高考江苏卷物理",
            ),
        )
        conn.execute(
            """
            INSERT INTO questions (
                question_id, canonical_title, question_type, difficulty, module, topic3, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "q-related",
                "仅包含部分重力磁场条件的相关题",
                "calculation",
                4,
                "electromagnetism",
                "带电粒子在复合场中的运动",
                "2008年江苏模拟题",
            ),
        )
        conn.execute(
            """
            INSERT INTO question_text_index (
                question_id, title_text, stem_text, answer_text, analysis_text, tags_json, source_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "q-related",
                "复合场中的带电小球",
                "带正电小球在电场和磁场中运动，重力加速度为g，求最大距离。",
                "略",
                "将运动分解后求解，洛伦兹力提供向心力qvB=mv²/R。",
                "[]",
                "2008年江苏模拟题",
            ),
        )
        conn.commit()

    result = module.search_questions(
        query="重力配速法",
        search_mode="comprehensive",
        year=2008,
        region="江苏",
        limit=10,
    )

    assert result["method_search"]["scanned_all_filtered_questions"] is True
    assert result["total"] == 2
    assert result["items"][0]["question_id"] == "Q00000298"
    assert result["items"][0]["method_match"]["level"] == "structural"
    assert "方法结构" in result["items"][0]["search_match"]["matched_sources"]
    assert "题干" in result["items"][0]["search_match"]["matched_locations"]["静止释放"]

    dedicated = module.search_method_questions(
        "重力配速法", year=2008, region="江苏", limit=10
    )
    assert dedicated["items"][0]["question_id"] == "Q00000298"
    assert dedicated["total"] == 1
    assert dedicated["method_search"]["confirmed_count"] == 1
    assert dedicated["method_search"]["related_candidate_count"] == 1
    assert dedicated["method_search"]["confirmed_only"] is True
    assert dedicated["response_mode"] == "compact"
    assert dedicated["evidence_included"] is False
    assert dedicated["items"][0]["method_level"] == "structural"
    assert len(dedicated["items"][0]["title"]) <= 80
    assert "stem_text" not in dedicated["items"][0]
    assert "method_match" not in dedicated["items"][0]

    full = module.search_method_questions(
        "重力配速法",
        year=2008,
        region="江苏",
        limit=10,
        summary_only=False,
        include_evidence=True,
    )
    assert full["response_mode"] == "full"
    assert full["evidence_included"] is True
    assert "stem_text" in full["items"][0]
    assert full["items"][0]["method_match"]["evidence"]
    assert full["items"][0]["search_match"]["matched_locations"]

    expanded = module.search_method_questions(
        "重力配速法",
        year=2008,
        region="江苏",
        limit=10,
        confirmed_only=False,
    )
    assert expanded["total"] == 2
    assert expanded["items"][1]["question_id"] == "q-related"
    assert expanded["items"][1]["method_level"] == "related"


def test_canonical_duplicate_scan_and_hash_backfill_are_safe(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "INSERT INTO questions (question_id, canonical_title, question_type, difficulty, module, source) VALUES (?, ?, ?, ?, ?, ?)",
            ("q-002", "Newton second law", "single_choice", 1, "mechanics", "another paper"),
        )
        conn.execute(
            "INSERT INTO question_text_index (question_id, title_text, stem_text, answer_text, tags_json) VALUES (?, ?, ?, ?, ?)",
            ("q-002", "Newton second law", "A force acts on a cart.", "A", "[]"),
        )

    scan = module.scan_canonical_duplicate_questions()
    assert scan["database_scope"] == "canonical_read_only"
    assert scan["group_count"] == 1
    assert scan["groups"][0]["recommended_primary_question_id"] == "q-001"
    assert scan["groups"][0]["duplicate_question_ids"] == ["q-002"]

    preview = module.backfill_canonical_question_hashes()
    assert preview["dry_run"] is True
    assert preview["changed_count"] == 2
    applied = module.backfill_canonical_question_hashes(dry_run=False)
    assert applied["audit_batch_id"]
    with sqlite3.connect(standard_db) as conn:
        rows = conn.execute("SELECT content_hash FROM questions ORDER BY question_id").fetchall()
    assert rows[0][0] and rows[0][0] == rows[1][0]


def test_canonical_duplicate_merge_archives_and_restores_without_deletion(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "UPDATE question_text_index SET tags_json = ? WHERE question_id = 'q-001'",
            ('["mechanics"]',),
        )
        conn.execute(
            "INSERT INTO questions (question_id, canonical_title, question_type, difficulty, module, source) VALUES (?, ?, ?, ?, ?, ?)",
            ("q-002", "Newton second law", "single_choice", 1, "mechanics", "paper two"),
        )
        conn.execute(
            "INSERT INTO question_text_index (question_id, title_text, stem_text, answer_text, tags_json) VALUES (?, ?, ?, ?, ?)",
            ("q-002", "Newton second law", "A force acts on a cart.", "A", '["dynamics"]'),
        )
        conn.execute(
            "INSERT INTO question_sources (source_id, question_id, source_label) VALUES (?, ?, ?)",
            ("source-q2", "q-002", "paper two"),
        )
        conn.execute(
            "INSERT INTO question_knowledge_points (link_id, question_id, topic3_id, rank) VALUES (?, ?, ?, ?)",
            ("qkp-q2", "q-002", "KP-MECH-DYN-NEWTON2", 1),
        )

    preview = module.merge_canonical_duplicate_questions("q-001", ["q-002"])
    assert preview["dry_run"] is True
    assert preview["merge_plan"]["knowledge_topic3_ids_to_add"] == ["KP-MECH-DYN-NEWTON2"]
    applied = module.merge_canonical_duplicate_questions(
        "q-001", ["q-002"], dry_run=False, plan_token=preview["plan_token"]
    )
    assert applied["archived_count"] == 1
    listed = module.list_canonical_duplicate_merges()
    assert listed["items"][0]["merge_batch_id"] == applied["audit_batch_id"]
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT status FROM questions WHERE question_id = 'q-002'").fetchone()[0] == "archived_duplicate"
        assert json.loads(conn.execute("SELECT tags_json FROM question_text_index WHERE question_id = 'q-001'").fetchone()[0]) == ["mechanics", "dynamics"]
        assert conn.execute("SELECT question_id FROM question_sources WHERE source_id = 'source-q2'").fetchone()[0] == "q-001"
        assert conn.execute("SELECT COUNT(*) FROM question_knowledge_points WHERE question_id = 'q-001'").fetchone()[0] == 1

    restore_preview = module.restore_canonical_duplicate_merge(applied["audit_batch_id"])
    restored = module.restore_canonical_duplicate_merge(
        applied["audit_batch_id"], dry_run=False, plan_token=restore_preview["plan_token"]
    )
    assert restored["ok"] is True
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT status FROM questions WHERE question_id = 'q-002'").fetchone()[0] == "approved"
        assert json.loads(conn.execute("SELECT tags_json FROM question_text_index WHERE question_id = 'q-001'").fetchone()[0]) == ["mechanics"]
        assert conn.execute("SELECT question_id FROM question_sources WHERE source_id = 'source-q2'").fetchone()[0] == "q-002"
        assert conn.execute("SELECT COUNT(*) FROM question_knowledge_points WHERE question_id = 'q-001'").fetchone()[0] == 0


def test_topic_search_merges_structured_and_legacy_metadata(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "UPDATE question_text_index SET tags_json = ? WHERE question_id = ?",
            (json.dumps(["\u8ffd\u53ca"], ensure_ascii=False), "q-001"),
        )
        conn.execute(
            """
            INSERT INTO questions (question_id, canonical_title, question_type, difficulty, module, source)
            VALUES ('q-002', 'kinematics item', 'single_choice', 2, 'mechanics', 'unit')
            """
        )
        conn.execute(
            "INSERT INTO question_text_index (question_id, title_text, stem_text, tags_json) VALUES ('q-002', 'kinematics item', '', '[]')"
        )
        conn.execute(
            """
            UPDATE knowledge_points SET topic3_name = ? WHERE topic3_id = 'KP-MECH-DYN-NEWTON2'
            """,
            ("\u5300\u53d8\u901f\u76f4\u7ebf\u8fd0\u52a8",),
        )
        conn.execute(
            """
            INSERT INTO question_knowledge_points (link_id, question_id, topic3_id)
            VALUES ('link-002', 'q-002', 'KP-MECH-DYN-NEWTON2')
            """
        )
    monkeypatch.setattr(
        module,
        "_fetch_formal_question_summaries",
        lambda ids: {question_id: {"question_id": question_id} for question_id in ids},
    )

    result = module.search_topic_questions("\u5300\u53d8\u901f")

    by_id = {item["question_id"]: item for item in result["items"]}
    assert set(by_id) == {"q-001", "q-002"}
    assert by_id["q-001"]["search_match"]["metadata_quality"] == "legacy_only"
    assert by_id["q-002"]["search_match"]["metadata_quality"] == "structured"
    assert result["unbound_legacy_question_ids"] == ["q-001"]


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
    assert batch["items"][0]["before_value"] == ["mechanics", "basic", "mechanics"]

    rollback_preview = module.rollback_change_batch(applied["audit_batch_id"])
    assert rollback_preview["dry_run"] is True
    assert rollback_preview["changed_count"] == 1
    assert rollback_preview["items"][0]["status"] == "will_rollback"

    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo tag normalization",
        plan_token=rollback_preview["plan_token"],
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

    applied = module.return_question_to_review(
        "q-001", reason="needs rework", dry_run=False, plan_token=preview["plan_token"]
    )
    assert applied["dry_run"] is False
    assert applied["audit_batch_id"]
    assert applied["operation_id"]
    assert applied["delivery_status"] == "delivered"

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT status, review_status FROM questions WHERE question_id='q-001'").fetchone() == ("待校对", "reviewing")
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='review_queue'").fetchone() is None
        assert conn.execute(
            "SELECT delivery_status FROM review_queue_outbox WHERE operation_id = ?",
            (applied["operation_id"],),
        ).fetchone()[0] == "delivered"

    with sqlite3.connect(review_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 1

    rollback_preview = module.rollback_change_batch(applied["audit_batch_id"], reason="undo return to review")
    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo return to review",
        plan_token=rollback_preview["plan_token"],
    )
    assert rollback["ok"] is True
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT status, review_status FROM questions WHERE question_id='q-001'").fetchone() == ("approved", "confirmed")
    with sqlite3.connect(review_db) as conn:
        assert conn.execute("SELECT status FROM review_queue WHERE entity_id='q-001'").fetchone()[0] == "rolled_back"


def test_review_queue_outbox_reconciles_pending_delivery(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)

    preview = module.return_question_to_review("q-001", reason="needs rework")
    applied = module.return_question_to_review(
        "q-001", reason="needs rework", dry_run=False, plan_token=preview["plan_token"]
    )
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "UPDATE review_queue_outbox SET delivery_status = 'pending' WHERE operation_id = ?",
            (applied["operation_id"],),
        )
    with sqlite3.connect(review_db) as conn:
        conn.execute("DELETE FROM review_queue WHERE review_id = ?", (applied["item"]["review_id"],))

    reconciled = module.reconcile_review_queue_outbox()

    assert reconciled["delivered_count"] == 1
    with sqlite3.connect(review_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 1


def test_rollback_cancels_pending_review_queue_outbox(tmp_path, monkeypatch):
    module = _load_mcp_server()
    standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)

    preview = module.return_question_to_review("q-001", reason="needs rework")
    applied = module.return_question_to_review(
        "q-001", reason="needs rework", dry_run=False, plan_token=preview["plan_token"]
    )
    with sqlite3.connect(standard_db) as conn:
        conn.execute(
            "UPDATE review_queue_outbox SET delivery_status = 'pending' WHERE operation_id = ?",
            (applied["operation_id"],),
        )

    rollback_preview = module.rollback_change_batch(applied["audit_batch_id"], reason="undo pending return to review")
    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo pending return to review",
        plan_token=rollback_preview["plan_token"],
    )
    assert rollback["ok"] is True
    assert rollback["cancelled_outbox_count"] == 1

    reconciled = module.reconcile_review_queue_outbox()
    assert reconciled["ok"] is True
    assert reconciled["attempted_count"] == 0
    with sqlite3.connect(standard_db) as conn:
        assert conn.execute(
            "SELECT delivery_status FROM review_queue_outbox WHERE operation_id = ?",
            (applied["operation_id"],),
        ).fetchone()[0] == "cancelled"
    with sqlite3.connect(review_db) as conn:
        assert conn.execute("SELECT status FROM review_queue WHERE entity_id = 'q-001'").fetchone()[0] == "rolled_back"


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

    rollback_preview = module.rollback_change_batch(applied["audit_batch_id"], reason="undo knowledge binding")
    rollback = module.rollback_change_batch(
        applied["audit_batch_id"],
        dry_run=False,
        reason="undo knowledge binding",
        plan_token=rollback_preview["plan_token"],
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
        plan_token=preview["plan_token"],
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

    updates = [{"question_id": "draft-001", "stem": "A force acts on a cart with mass m."}]
    preview = module.update_review_task_draft(
        "task-review-001",
        updates,
        reason="fix draft wording",
    )
    assert preview["requires_confirmation"] is True

    missing = module.update_review_task_draft(
        "task-review-001",
        updates,
        dry_run=False,
        reason="fix draft wording",
    )
    assert missing["error_info"]["code"] == "PLAN_TOKEN_REQUIRED"

    applied = module.update_review_task_draft(
        "task-review-001",
        updates,
        dry_run=False,
        reason="fix draft wording",
        plan_token=preview["plan_token"],
    )
    assert applied["dry_run"] is False
    assert applied["idempotent"] is False

    replay = module.update_review_task_draft(
        "task-review-001",
        updates,
        dry_run=False,
        reason="fix draft wording",
        plan_token=preview["plan_token"],
    )
    assert replay["idempotent"] is True

    with sqlite3.connect(review_db) as conn:
        saved = conn.execute("SELECT result_json FROM import_pipeline_tasks WHERE task_id='task-review-001'").fetchone()[0]
    assert "mass m" in saved

    with sqlite3.connect(standard_db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='import_pipeline_tasks'").fetchone() is None


def test_validate_review_task_returns_structured_risks(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, _review_db = _configure_paths(module, tmp_path, monkeypatch)

    result = module.validate_review_task("task-review-001")

    assert result["ok"] is True
    assert result["question_count"] == 1
    assert result["risk_question_count"] == 1
    assert result["summary"]["warning"] >= 1
    risks = result["items"][0]["risks"]
    codes = {risk["code"] for risk in risks}
    assert "missing_options" not in codes
    assert "missing_knowledge" in codes
    assert "missing_source" in codes
    assert result["task_warnings"] == ["needs answer check"]
    assert result["workflow"]["state"] == "needs_cleanup"
    assert "organize_knowledge_tree" in result["workflow"]["next_tools"]
    assert all({"code", "severity", "field", "message", "suggestion"} <= set(risk) for risk in risks)


def test_validate_review_task_detects_answer_image_and_latex_mismatches(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-risk-001",
                "question_type": "single_choice",
                "title": "题干 image:fig-missing $x",
                "options": [{"label": "A", "text": "甲"}, {"label": "B", "text": "乙"}],
                "answer": "C",
                "figures": [{"asset_id": "fig-unused"}],
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    result = module.validate_review_task("task-review-001", require_knowledge=False, require_source=False)
    codes = {risk["code"] for risk in result["items"][0]["risks"]}

    assert {"answer_option_mismatch", "missing_figure", "unused_figure", "unbalanced_latex"} <= codes


def test_validate_review_task_does_not_treat_successful_metadata_extraction_as_risk(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-import-note",
                "question_type": "calculation",
                "title": "已知物体受恒力作用，求其加速度。",
                "answer": "a=F/m",
                "validation_warnings": [
                    "已从答案中提取难度元数据。",
                    "题干具有明确的多步骤实验结构，题型已修正为实验题。",
                ],
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    result = module.validate_review_task(
        "task-review-001", require_knowledge=False, require_source=False, risks_only=True
    )

    assert result["risk_question_count"] == 0
    assert result["items"] == []


def test_validate_review_task_supports_risks_only_and_legal_display_math(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-clean",
                "question_type": "calculation",
                "title": "计算题",
                "stem": "$$F=ma$$ 且 $v=at$。",
                "answer": "正确",
            },
            {
                "question_id": "draft-risk",
                "question_type": "single_choice",
                "title": "选择题",
                "options": [{"label": "A", "text": "只有一个选项"}],
                "answer": "B",
            },
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    all_items = module.validate_review_task("task-review-001", require_knowledge=False, require_source=False)
    result = module.validate_review_task(
        "task-review-001", require_knowledge=False, require_source=False, risks_only=True
    )

    assert all_items["clean"] is False
    assert all_items["question_count"] == 2
    assert all_items["items"][0]["risk_count"] == 0
    assert result["risks_only"] is True
    assert result["question_count"] == 2
    assert result["returned_question_count"] == 1
    assert [item["question_id"] for item in result["items"]] == ["draft-risk"]


def test_validate_review_task_reports_latex_and_choice_type_mismatch(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-format-risk",
                "question_type": "single_choice",
                "title": "检查格式",
                "stem": "$$F=ma$",
                "options": [
                    {"label": "A", "text": "选项 A"},
                    {"label": "B", "text": "选项 B"},
                ],
                "answer": "A、B",
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    result = module.validate_review_task(
        "task-review-001", require_knowledge=False, require_source=False, risks_only=True
    )
    codes = {risk["code"] for risk in result["items"][0]["risks"]}

    assert {"malformed_latex", "choice_type_mismatch"} <= codes
    assert "split_merged_options" in result["workflow"]["next_tools"]


def test_latex_risk_workflow_guides_mcp_to_manually_standardize_draft(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-manual-latex",
                "question_type": "calculation",
                "title": "公式格式待修复",
                "stem": "由 $$F=ma$ 可知 $a=F/m。",
                "answer": "见解析",
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    result = module.validate_review_task(
        "task-review-001", require_knowledge=False, require_source=False, risks_only=True
    )

    action = next(item for item in result["workflow"]["actions"] if item["mode"] == "manual_standardization")
    assert action["tool"] == "update_review_task_draft"
    assert "get_review_task_full" in result["workflow"]["next_tools"]
    assert "行内公式用 $...$" in action["message"]


def test_latex_cleanup_requires_plan_token_and_replays_once(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-latex",
                "question_type": "calculation",
                "title": "公式清理",
                "stem": "由 *F* = *ma* 可知加速度。",
                "answer": "见解析",
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    preview = module.clean_review_task_latex("task-review-001", reason="统一公式格式")
    assert preview["changed_count"] == 1
    assert preview["requires_confirmation"] is True

    missing = module.clean_review_task_latex(
        "task-review-001", dry_run=False, reason="统一公式格式"
    )
    assert missing["error_info"]["code"] == "PLAN_TOKEN_REQUIRED"

    applied = module.clean_review_task_latex(
        "task-review-001",
        dry_run=False,
        reason="统一公式格式",
        plan_token=preview["plan_token"],
    )
    assert applied["idempotent"] is False
    saved = module.get_review_task_full("task-review-001", include_knowledge=False)
    assert saved["questions"][0]["stem"] == "由 $F$ = $ma$ 可知加速度。"

    replay = module.clean_review_task_latex(
        "task-review-001",
        dry_run=False,
        reason="统一公式格式",
        plan_token=preview["plan_token"],
    )
    assert replay["idempotent"] is True


def test_deduplicate_review_task_questions_removes_only_exact_content_duplicates(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-keep",
                "question_type": "single_choice",
                "title": "已知电阻 R 接入电路后的电流变化如图所示。![fig:one]",
                "options": [{"label": "A", "text": "增大"}, {"label": "B", "text": "减小"}],
                "answer": "A",
                "analysis": "由欧姆定律可得。",
                "source": "2026 模拟卷",
            },
            {
                "question_id": "draft-remove",
                "question_type": "single_choice",
                "title": "已知电阻 R 接入电路后的电流变化如图所示。![fig:two]",
                "options": [{"label": "A", "text": "增大"}, {"label": "B", "text": "减小"}],
                "answer": "A",
                "analysis": "由欧姆定律可得。",
                "source": "2026 模拟卷",
            },
            {
                "question_id": "draft-distinct",
                "question_type": "single_choice",
                "title": "已知电阻 R 接入电路后的电流变化如图所示，求功率变化。",
                "options": [{"label": "A", "text": "增大"}, {"label": "B", "text": "减小"}],
                "answer": "B",
                "analysis": "由功率公式可得。",
                "source": "2026 模拟卷",
            },
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    preview = module.deduplicate_review_task_questions("task-review-001", reason="删除重复导入题")
    assert preview["dry_run"] is True
    assert preview["duplicate_group_count"] == 1
    assert preview["removed_count"] == 1
    assert preview["items"] == [{"kept_question_id": "draft-keep", "removed_question_ids": ["draft-remove"], "count": 2}]

    applied = module.deduplicate_review_task_questions(
        "task-review-001",
        dry_run=False,
        reason="删除重复导入题",
        plan_token=preview["plan_token"],
    )
    assert applied["remaining_question_count"] == 2
    saved = module.get_review_task_full("task-review-001", include_knowledge=False)
    assert [item["question_id"] for item in saved["questions"]] == ["draft-keep", "draft-distinct"]


def test_review_draft_write_rejects_changes_after_preview(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)

    updates = [{"question_id": "draft-001", "source": "new source"}]
    preview = module.update_review_task_draft("task-review-001", updates, reason="update source")
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET updated_at = ? WHERE task_id = 'task-review-001'",
            ("changed-after-preview",),
        )

    result = module.update_review_task_draft(
        "task-review-001",
        updates,
        dry_run=False,
        reason="update source",
        plan_token=preview["plan_token"],
    )

    assert result["ok"] is False
    assert result["error_info"]["code"] == "OPERATION_PLAN_VERSION_CONFLICT"


def test_split_merged_options_uses_raw_text_and_writes_back(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-merged",
                "question_type": "single_choice",
                "title": "合并选项题",
                "raw_text": "A．0.13 B．0.3 C．3.33 D．7.5",
                "options": [{"opt": "A", "content": "0.13 B．0.3 C．3.33 D．7.5"}],
                "answer": "D",
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    preview = module.split_merged_options("task-review-001", reason="修复 OCR 合并选项")
    assert preview["dry_run"] is True
    assert preview["changed_count"] == 1
    assert [item["label"] for item in preview["items"][0]["options"]] == ["A", "B", "C", "D"]

    applied = module.split_merged_options(
        "task-review-001",
        dry_run=False,
        reason="修复 OCR 合并选项",
        plan_token=preview["plan_token"],
    )
    assert applied["changed_count"] == 1
    assert applied["validation"]["ok"] is True
    assert applied["manual_action_required"] is True
    assert applied["validation"]["workflow"]["state"] == "needs_cleanup"
    with sqlite3.connect(review_db) as conn:
        saved = json.loads(conn.execute(
            "SELECT result_json FROM import_pipeline_tasks WHERE task_id = 'task-review-001'"
        ).fetchone()[0])
    assert [option["opt"] for option in saved["questions"][0]["options"]] == ["A", "B", "C", "D"]


def test_split_merged_options_expands_two_ocr_rows_using_the_quoted_option_block(tmp_path, monkeypatch):
    module = _load_mcp_server()
    _standard_db, review_db = _configure_paths(module, tmp_path, monkeypatch)
    payload = {
        "questions": [
            {
                "question_id": "draft-two-rows",
                "question_type": "single_choice",
                "title": "选择题",
                "raw_text": "题干\n\n> A．甲 B．乙\n> C．丙 D．丁\n\n【答案】B\n【解析】B 正确",
                "options": [
                    {"opt": "A", "content": "甲 B．乙"},
                    {"opt": "C", "content": "丙 D．丁"},
                ],
                "answer": "B",
            }
        ]
    }
    with sqlite3.connect(review_db) as conn:
        conn.execute(
            "UPDATE import_pipeline_tasks SET result_json = ? WHERE task_id = 'task-review-001'",
            (json.dumps(payload, ensure_ascii=False),),
        )

    preview = module.split_merged_options("task-review-001")

    assert preview["changed_count"] == 1
    assert preview["items"][0]["options"] == [
        {"label": "A", "text": "甲"},
        {"label": "B", "text": "乙"},
        {"label": "C", "text": "丙"},
        {"label": "D", "text": "丁"},
    ]


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

    result = module.submit_word_export_job({"id": "lesson-001", "questions": [], "nodes": []}, confirmed=True)

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
        confirmed=True,
    )

    assert result["ok"] is True
    assert result["audit_id"] == "audit-export"
    assert result["job"]["download_url"] == "/api/tasks/export-002/download"
    assert "input_summary" not in result["job"]


def test_direct_high_risk_submissions_require_explicit_confirmation(monkeypatch):
    module = _load_mcp_server()
    monkeypatch.setattr(module, "_task_center_service", lambda: pytest.fail("must not submit"))
    monkeypatch.setattr(module, "_import_service", lambda: pytest.fail("must not create review task"))

    review = module.submit_ai_generated_review("generated question")
    imported = module.submit_import_job("batch-1")
    cleaned = module.submit_ai_clean_job("batch-1")
    exported = module.submit_word_export_job({"id": "lesson-1", "questions": [{}], "nodes": []})

    assert all(item["confirmation_required"] is True for item in (review, imported, cleaned, exported))
    assert exported["target"]["question_count"] == 1
