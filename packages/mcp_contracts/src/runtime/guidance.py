"""Read-only workflow guidance for MCP clients."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any


WORKFLOW_GUIDES: tuple[dict[str, Any], ...] = (
    {
        "id": "question_search",
        "title": "查题与筛选",
        "intents": ["查题", "检索", "搜索", "筛选"],
        "tools": ["list_filter_facets", "search_questions_compact", "get_questions_by_ids", "download_question_images"],
        "boundary": "先返回紧凑题卡，只为最终选中的题读取完整正文或下载图片。",
    },
    {
        "id": "method_search",
        "title": "按方法、模型或相似结构找题",
        "intents": ["方法", "模型", "相似", "母题", "经典题"],
        "tools": ["search_method_questions", "find_similar_questions", "get_questions_by_ids", "record_method_retrieval_feedback"],
        "boundary": "区分明确命中、结构命中和仅相关候选；教师确认后才记录检索反馈。",
    },
    {
        "id": "composition",
        "title": "组卷工作台",
        "intents": ["组卷", "选题", "试卷", "工作台", "编排"],
        "tools": ["search_questions_curated", "create_composition_workbench", "apply_composition_workbench_plan", "preview_composition_workbench", "export_composition_workbench"],
        "boundary": "只修改组卷草稿，不修改正式题目；批量方案可先 dry_run。",
    },
    {
        "id": "saved_handout",
        "title": "已保存讲义与 Word 排版",
        "intents": ["讲义", "Word", "排版", "已保存讲义", "版本"],
        "tools": ["list_saved_handouts", "get_saved_handout", "list_saved_handout_versions", "apply_word_format_to_saved_handout", "export_saved_handout", "restore_saved_handout_version"],
        "boundary": "已保存讲义与工作台草稿是不同文档；恢复和覆盖排版需要预览或确认。",
    },
    {
        "id": "teaching_project",
        "title": "教学项目、课件与课堂",
        "intents": ["课件", "幻灯片", "课堂", "发布", "教学项目"],
        "tools": ["get_teaching_project_status", "preflight_teaching_handout", "sync_teaching_slides", "publish_teaching_artifact", "start_classroom_session"],
        "boundary": "同步、发布前先检查差异；课堂只从已发布课件启动。",
    },
    {
        "id": "review_center",
        "title": "导入与审核中心",
        "intents": ["导入", "审核", "校对", "草稿", "送审", "公式修复"],
        "tools": ["list_review_tasks", "get_review_task_full", "validate_review_task", "clean_review_task_latex", "split_merged_options", "update_review_task_draft"],
        "boundary": "审核草稿只写审核库；修复后再次校验，不直接修改正式题目正文。",
    },
    {
        "id": "catalog_maintenance",
        "title": "正式题库元数据维护",
        "intents": ["标签", "知识点", "元数据", "题库维护", "重复题", "回滚"],
        "tools": ["database_health_report", "diagnose_tag_maintenance", "maintain_question_tags", "maintain_question_knowledge_points", "scan_canonical_duplicate_questions", "list_change_batches"],
        "boundary": "正式库维护必须保留审计批次；正文问题走送回审核流程。",
    },
    {
        "id": "background_jobs",
        "title": "后台任务",
        "intents": ["任务", "导出任务", "后台", "重试", "取消"],
        "tools": ["list_jobs", "get_job_status", "submit_import_job", "submit_word_export_job", "retry_job", "cancel_job"],
        "boundary": "提交任务返回审计编号；重试和取消必须明确确认目标任务。",
    },
)


def build_workflow_guide(
    intent: str | None,
    *,
    profile: str,
    exposed_tools: Collection[str],
) -> dict[str, Any]:
    """Return profile-aware workflow suggestions without running a tool."""
    query = str(intent or "").strip().casefold()
    exposed = set(exposed_tools)
    matched: list[dict[str, Any]] = []
    for guide in WORKFLOW_GUIDES:
        terms = [str(term).casefold() for term in guide["intents"]]
        if query and not any(term in query or query in term for term in terms):
            continue
        available_tools = [name for name in guide["tools"] if name in exposed]
        matched.append(
            {
                **guide,
                "tools": available_tools,
                "unavailable_tools": [name for name in guide["tools"] if name not in exposed],
                "start_tool": available_tools[0] if available_tools else None,
            }
        )
    if query and not matched:
        matched = [
            {
                **guide,
                "tools": [name for name in guide["tools"] if name in exposed],
                "unavailable_tools": [name for name in guide["tools"] if name not in exposed],
                "start_tool": next((name for name in guide["tools"] if name in exposed), None),
            }
            for guide in WORKFLOW_GUIDES
        ]
    return {
        "ok": True,
        "profile": profile,
        "intent": intent,
        "matched_count": len(matched),
        "workflows": matched,
        "global_rules": [
            "正式题库、审核库、组卷草稿和已保存讲义是不同边界。",
            "先使用紧凑读取；只为最终目标读取完整正文、图片或大体量结果。",
            "带 dry_run、confirmed 或 plan_token 的操作必须遵守其确认协议。",
        ],
    }
