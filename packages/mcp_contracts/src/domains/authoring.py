"""Registration boundary for the authoring MCP domain (MCP-103)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from ..tool_registry import ToolDomain, ToolRegistry

ToolHandler = Callable[..., Any]
ToolDecoratorFactory = Callable[[], Callable[[ToolHandler], ToolHandler]]


class AuthoringDomain:
    """Compatibility facade for authoring workspaces and teaching artifacts.

    Legacy handlers are injected by the entrypoint.  The facade keeps the public
    MCP signatures stable while isolating workbench, teaching-project, classroom,
    handout and paper-authoring registration from the monolithic transport file.
    """

    def __init__(self, handlers: Mapping[str, ToolHandler]) -> None:
        self._handlers = handlers

    def _call(self, name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._handlers[name](*args, **kwargs)

    def list_teaching_projects(self, limit: int=50) -> dict[str, Any]:
        return self._call("list_teaching_projects", limit)

    def get_teaching_project(self, project_id: str) -> dict[str, Any]:
        return self._call("get_teaching_project", project_id)

    def get_teaching_project_status(self, project_id: str) -> dict[str, Any]:
        return self._call("get_teaching_project_status", project_id)

    def duplicate_teaching_project(self, project_id: str, title: str | None=None) -> dict[str, Any]:
        return self._call("duplicate_teaching_project", project_id, title)

    def publish_teaching_artifact(self, project_id: str, artifact: Literal['handout', 'slides']='slides', confirmed: bool=False) -> dict[str, Any]:
        return self._call("publish_teaching_artifact", project_id, artifact, confirmed)

    def preflight_teaching_handout(self, project_id: str, use_published: bool=False) -> dict[str, Any]:
        return self._call("preflight_teaching_handout", project_id, use_published)

    def sync_teaching_slides(self, project_id: str, strategy: Literal['preserve_manual', 'replace']='preserve_manual', confirmed: bool=False) -> dict[str, Any]:
        return self._call("sync_teaching_slides", project_id, strategy, confirmed)

    def start_classroom_session(self, project_id: str) -> dict[str, Any]:
        return self._call("start_classroom_session", project_id)

    def get_classroom_session(self, session_id: str) -> dict[str, Any]:
        return self._call("get_classroom_session", session_id)

    def update_classroom_session(self, session_id: str, current_index: int | None=None, display_mode: Literal['stem_only', 'stem_answer', 'full'] | None=None, reveal_step: int | None=None, teacher_notes: str | None=None, annotations: dict[str, str] | None=None) -> dict[str, Any]:
        return self._call("update_classroom_session", session_id, current_index, display_mode, reveal_step, teacher_notes, annotations)

    def end_classroom_session(self, session_id: str) -> dict[str, Any]:
        return self._call("end_classroom_session", session_id)

    def list_composition_workbenches(self, limit: int=20) -> dict[str, Any]:
        return self._call("list_composition_workbenches", limit)

    def get_composition_workbench(self, draft_id: str | None=None) -> dict[str, Any]:
        return self._call("get_composition_workbench", draft_id)

    def create_composition_workbench(self, title: str, subtitle: str | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("create_composition_workbench", title, subtitle, dry_run)

    def add_questions_to_composition_workbench(self, question_ids: list[str], draft_id: str | None=None, insert_at: int | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("add_questions_to_composition_workbench", question_ids, draft_id, insert_at, dry_run)

    def add_knowledge_to_composition_workbench(self, topic3_ids: list[str], draft_id: str | None=None, insert_at: int | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("add_knowledge_to_composition_workbench", topic3_ids, draft_id, insert_at, dry_run)

    def insert_teaching_block_to_composition_workbench(self, title: str, content: str='', block_kind: Literal['body', 'exam_title', 'name_line', 'section_title', 'text_box']='body', draft_id: str | None=None, insert_at: int | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("insert_teaching_block_to_composition_workbench", title, content, block_kind, draft_id, insert_at, dry_run)

    def reorder_composition_workbench(self, ordered_item_ids: list[str] | None=None, draft_id: str | None=None, dry_run: bool=False, item_id: str | None=None, after_item_id: str | None=None) -> dict[str, Any]:
        return self._call("reorder_composition_workbench", ordered_item_ids, draft_id, dry_run, item_id, after_item_id)

    def move_composition_item(self, item_id: str, after_item_id: str | None=None, draft_id: str | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("move_composition_item", item_id, after_item_id, draft_id, dry_run)

    def remove_items_from_composition_workbench(self, item_ids: list[str], draft_id: str | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("remove_items_from_composition_workbench", item_ids, draft_id, dry_run)

    def update_composition_item(self, item_id: str, payload: dict[str, Any], draft_id: str | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("update_composition_item", item_id, payload, draft_id, dry_run)

    def lock_composition_workbench(self, locked: bool=True, draft_id: str | None=None, reason: str | None=None) -> dict[str, Any]:
        return self._call("lock_composition_workbench", locked, draft_id, reason)

    def apply_composition_workbench_plan(self, operations: list[dict[str, Any]], draft_id: str | None=None, ordered_refs: list[str] | None=None, mode: Literal['full', 'patch']='patch', dry_run: bool=False) -> dict[str, Any]:
        return self._call("apply_composition_workbench_plan", operations, draft_id, ordered_refs, mode, dry_run)

    def preview_composition_workbench(self, draft_id: str | None=None, format: Literal['markdown', 'html']='markdown') -> dict[str, Any]:
        return self._call("preview_composition_workbench", draft_id, format)

    def export_composition_workbench(self, draft_id: str | None=None, format: Literal['word', 'pptx']='word', include_answers: bool | None=None, include_analysis: bool | None=None, file_name: str | None=None, template_id: str | None=None, format_spec: dict[str, Any] | None=None, answer_position: Literal['after_question', 'end'] | None=None) -> dict[str, Any]:
        return self._call("export_composition_workbench", draft_id, format, include_answers, include_analysis, file_name, template_id, format_spec, answer_position)

    def list_word_export_templates(self, ) -> dict[str, Any]:
        return self._call("list_word_export_templates")

    def get_word_export_template(self, template_id: str) -> dict[str, Any]:
        return self._call("get_word_export_template", template_id)

    def propose_word_export_format(self, purpose: Literal['formal_exam', 'student_practice', 'teacher_handout', 'custom']='formal_exam', requirements: str | None=None) -> dict[str, Any]:
        return self._call("propose_word_export_format", purpose, requirements)

    def validate_word_export_format(self, format_spec: dict[str, Any]) -> dict[str, Any]:
        return self._call("validate_word_export_format", format_spec)

    def save_word_export_template(self, name: str, format_spec: dict[str, Any], template_id: str | None=None, description: str | None=None, overwrite: bool=False) -> dict[str, Any]:
        return self._call("save_word_export_template", name, format_spec, template_id, description, overwrite)

    def rename_word_export_template(self, template_id: str, name: str) -> dict[str, Any]:
        return self._call("rename_word_export_template", template_id, name)

    def list_saved_handouts(self, limit: int=100) -> dict[str, Any]:
        return self._call("list_saved_handouts", limit)

    def get_saved_handout(self, document_id: str) -> dict[str, Any]:
        return self._call("get_saved_handout", document_id)

    def list_saved_handout_versions(self, document_id: str) -> dict[str, Any]:
        return self._call("list_saved_handout_versions", document_id)

    def restore_saved_handout_version(self, document_id: str, version: int, confirmed: bool=False) -> dict[str, Any]:
        return self._call("restore_saved_handout_version", document_id, version, confirmed)

    def rename_saved_handout(self, document_id: str, title: str) -> dict[str, Any]:
        return self._call("rename_saved_handout", document_id, title)

    def apply_word_format_to_saved_handout(self, document_id: str, template_id: str | None=None, format_spec: dict[str, Any] | None=None) -> dict[str, Any]:
        return self._call("apply_word_format_to_saved_handout", document_id, template_id, format_spec)

    def apply_word_format_to_workbench(self, draft_id: str | None=None, template_id: str | None=None, format_spec: dict[str, Any] | None=None, dry_run: bool=True) -> dict[str, Any]:
        return self._call("apply_word_format_to_workbench", draft_id, template_id, format_spec, dry_run)

    def export_saved_handout(self, document_id: str, format: Literal['word']='word', include_answers: bool | None=None, include_analysis: bool | None=None, answer_position: Literal['after_question', 'end'] | None=None, template_id: str | None=None, format_spec: dict[str, Any] | None=None, file_name: str | None=None) -> dict[str, Any]:
        return self._call("export_saved_handout", document_id, format, include_answers, include_analysis, answer_position, template_id, format_spec, file_name)

    def curate_questions_to_composition_workbench(self, query: str, target_count: int=20, draft_id: str | None=None, insert_at: int | None=None, dry_run: bool=False) -> dict[str, Any]:
        return self._call("curate_questions_to_composition_workbench", query, target_count, draft_id, insert_at, dry_run)

    def create_paper(self, paper_id: str, name: str, year: int, region: str, exam_type: str) -> dict[str, Any]:
        return self._call("create_paper", paper_id, name, year, region, exam_type)

    def associate_questions_to_paper(self, question_ids: list[str], paper_id: str, reason: str | None=None) -> dict[str, Any]:
        return self._call("associate_questions_to_paper", question_ids, paper_id, reason)

    def export_questions_to_typst(self, question_ids: list[str], title: str | None=None, include_answers: bool=False, dry_run: bool=True) -> dict[str, Any]:
        return self._call("export_questions_to_typst", question_ids, title, include_answers, dry_run)


def authoring_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    """Return compatible MCP-103 names in catalogue order."""
    return tuple(spec.name for spec in registry.discover(domain=ToolDomain.AUTHORING))


def register_authoring_tools(
    tool: ToolDecoratorFactory,
    registry: ToolRegistry,
    handlers: Mapping[str, ToolHandler],
) -> tuple[str, ...]:
    """Bind all and only declared MCP-103 handlers to the MCP transport."""
    names = authoring_tool_names(registry)
    missing = [name for name in names if not callable(handlers.get(name))]
    if missing:
        raise RuntimeError(f"MCP-103 handlers are missing: {', '.join(missing)}")
    for name in names:
        tool()(handlers[name])
    return names
