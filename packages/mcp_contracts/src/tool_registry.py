"""Declarative registry for the Physics Vault MCP tool surface.

The registry is deliberately independent of the MCP SDK.  It is the single
source of truth for the public tool names, ownership domain, access mode and
risk level; the server only binds the implementation functions to these
declarations during startup.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Callable, Iterable


class ToolDomain(StrEnum):
    SEARCH = "search"
    MANAGEMENT = "management"
    REVIEW = "import_review"
    AUTHORING = "authoring"
    OPERATIONS = "operations"


class ToolRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ToolHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Public declaration and bound implementation for one MCP tool."""

    name: str
    domain: ToolDomain
    risk: ToolRisk
    read_only: bool
    input_model: inspect.Signature | None = None
    handler: ToolHandler | None = None


class DuplicateToolNameError(ValueError):
    """Raised before the MCP server starts when a name is declared twice."""


class ToolRegistry:
    def __init__(self, declarations: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in declarations:
            self.declare(spec)

    def declare(self, spec: ToolSpec) -> ToolSpec:
        if not spec.name:
            raise ValueError("MCP tool names must not be empty")
        if spec.name in self._specs:
            raise DuplicateToolNameError(f"Duplicate MCP tool name: {spec.name}")
        self._specs[spec.name] = spec
        return spec

    def bind(self, name: str, handler: ToolHandler) -> ToolSpec:
        try:
            spec = self._specs[name]
        except KeyError as exc:
            raise KeyError(f"MCP tool {name!r} has no ToolSpec declaration") from exc
        if spec.handler is not None:
            raise DuplicateToolNameError(f"MCP tool {name!r} was bound more than once")
        bound = replace(spec, handler=handler, input_model=inspect.signature(handler))
        self._specs[name] = bound
        return bound

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def discover(
        self,
        *,
        domain: ToolDomain | str | None = None,
        risk: ToolRisk | str | None = None,
        writable: bool | None = None,
    ) -> tuple[ToolSpec, ...]:
        """Return declarations filtered by domain, risk, or write capability."""
        selected = tuple(self._specs.values())
        if domain is not None:
            selected = tuple(spec for spec in selected if spec.domain == ToolDomain(domain))
        if risk is not None:
            selected = tuple(spec for spec in selected if spec.risk == ToolRisk(risk))
        if writable is not None:
            selected = tuple(spec for spec in selected if spec.read_only is not writable)
        return selected

    def names(self) -> frozenset[str]:
        return frozenset(self._specs)

    def assert_all_bound(self) -> None:
        unbound = sorted(spec.name for spec in self._specs.values() if spec.handler is None)
        if unbound:
            raise RuntimeError(f"Unbound MCP tool declarations: {', '.join(unbound)}")


def _names(value: str) -> tuple[str, ...]:
    return tuple(name for name in value.split() if name)


# This catalogue is the declaration layer.  Names stay exactly compatible with
# the existing MCP server while later tasks can move each domain independently.
_DOMAIN_TOOL_NAMES: dict[ToolDomain, tuple[str, ...]] = {
    ToolDomain.SEARCH: _names("""
        list_filter_facets search_questions search_method_questions download_question_images search_topic_questions
        get_questions_by_ids list_knowledge_tree search_knowledge_points get_question_knowledge_points
        list_question_tags list_method_retrieval_feedback method_retrieval_learning_report database_boundary_report
        database_health_report find_similar_questions scan_canonical_duplicate_questions list_canonical_duplicate_merges
    """),
    ToolDomain.MANAGEMENT: _names("""
        create_knowledge_points organize_knowledge_tree batch_update_question_metadata diagnose_tag_maintenance
        suggest_question_tags maintain_question_tags record_method_retrieval_feedback maintain_question_knowledge_points
        backfill_canonical_question_hashes merge_canonical_duplicate_questions restore_canonical_duplicate_merge
        batch_replace_question_tags batch_replace_question_knowledge_points return_question_to_review
        reconcile_review_queue_outbox list_change_batches get_change_batch rollback_change_batch
    """),
    ToolDomain.REVIEW: _names("""
        list_review_queue import_word_folder_to_review list_review_tasks get_review_task get_review_task_full
        validate_review_task find_duplicate_review_tasks delete_review_tasks suggest_knowledge_points_for_task
        clean_review_task_latex split_merged_options deduplicate_review_task_questions update_review_task_draft
        submit_ai_generated_review
    """),
    ToolDomain.AUTHORING: _names("""
        list_teaching_projects get_teaching_project get_teaching_project_status duplicate_teaching_project
        publish_teaching_artifact preflight_teaching_handout sync_teaching_slides start_classroom_session
        get_classroom_session update_classroom_session end_classroom_session list_composition_workbenches
        get_composition_workbench create_composition_workbench add_questions_to_composition_workbench
        add_knowledge_to_composition_workbench insert_teaching_block_to_composition_workbench
        reorder_composition_workbench move_composition_item remove_items_from_composition_workbench
        update_composition_item lock_composition_workbench apply_composition_workbench_plan preview_composition_workbench
        export_composition_workbench list_word_export_templates get_word_export_template propose_word_export_format
        validate_word_export_format save_word_export_template rename_word_export_template list_saved_handouts
        get_saved_handout list_saved_handout_versions restore_saved_handout_version rename_saved_handout
        apply_word_format_to_saved_handout apply_word_format_to_workbench export_saved_handout
        curate_questions_to_composition_workbench create_paper associate_questions_to_paper export_questions_to_typst
    """),
    ToolDomain.OPERATIONS: _names("""
        submit_import_job submit_ai_clean_job submit_word_export_job submit_pptx_export_job get_job_status
        list_jobs retry_job cancel_job
    """),
}

_READ_ONLY_PREFIXES = ("list_", "get_", "search_", "find_", "validate_", "diagnose_", "suggest_", "propose_", "preflight_", "preview_", "scan_", "database_")
_HIGH_RISK_PREFIXES = ("delete_", "rollback_", "merge_", "restore_", "return_", "batch_", "maintain_", "clean_", "split_", "deduplicate_", "import_", "submit_", "retry_", "cancel_", "publish_", "sync_", "lock_", "apply_", "backfill_")


def _read_only(name: str) -> bool:
    return name.startswith(_READ_ONLY_PREFIXES)


def _risk(name: str, read_only: bool) -> ToolRisk:
    if read_only:
        return ToolRisk.LOW
    if name.startswith(_HIGH_RISK_PREFIXES):
        return ToolRisk.HIGH
    return ToolRisk.MEDIUM


def default_tool_registry() -> ToolRegistry:
    declarations: list[ToolSpec] = []
    for domain, names in _DOMAIN_TOOL_NAMES.items():
        for name in names:
            read_only = _read_only(name)
            declarations.append(ToolSpec(name=name, domain=domain, risk=_risk(name, read_only), read_only=read_only))
    return ToolRegistry(declarations)


def discover_tools(
    *,
    domain: ToolDomain | str | None = None,
    risk: ToolRisk | str | None = None,
    writable: bool | None = None,
) -> tuple[ToolSpec, ...]:
    """Discover declared tools without importing the MCP transport runtime."""
    return default_tool_registry().discover(domain=domain, risk=risk, writable=writable)


def profile_tool_names(profile: str) -> frozenset[str]:
    """Compatibility profiles used by the monolithic MCP entrypoint."""
    normalized = profile.strip().lower()
    if normalized == "all":
        return default_tool_registry().names()
    aliases = {
        "catalog": ToolDomain.SEARCH,
        "catalog_maintenance": ToolDomain.MANAGEMENT,
        "review": ToolDomain.REVIEW,
        "authoring": ToolDomain.AUTHORING,
        "operations": ToolDomain.OPERATIONS,
    }
    domain = aliases.get(normalized)
    return frozenset(_DOMAIN_TOOL_NAMES.get(domain, ()))


__all__ = [
    "DuplicateToolNameError",
    "ToolDomain",
    "ToolRegistry",
    "ToolRisk",
    "ToolSpec",
    "default_tool_registry",
    "discover_tools",
    "profile_tool_names",
]
