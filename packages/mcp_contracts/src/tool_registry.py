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


class ToolImpactScope(StrEnum):
    NONE = "none"
    DOWNLOAD_CACHE = "download_cache"
    EXPORT_FILES = "export_files"
    WORKBENCH_DRAFT = "workbench_draft"
    SAVED_HANDOUT = "saved_handout"
    TEACHING_PROJECT = "teaching_project"
    CLASSROOM_SESSION = "classroom_session"
    CANONICAL_METADATA = "canonical_metadata"
    CANONICAL_CONTROLLED = "canonical_controlled"
    REVIEW_WORKSPACE = "review_workspace"
    TASK_QUEUE = "task_queue"


class ToolReversibility(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    REGENERABLE = "regenerable"
    VERSIONED = "versioned"
    AUDITED = "audited"
    SOFT_DELETE = "soft_delete"
    LIMITED = "limited"


class ToolConfirmation(StrEnum):
    NONE = "none"
    DIRECT = "direct"
    DRY_RUN = "dry_run"
    EXPLICIT = "explicit_confirmation"
    PLAN_TOKEN = "plan_token"


ToolHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Public declaration and bound implementation for one MCP tool."""

    name: str
    domain: ToolDomain
    risk: ToolRisk
    read_only: bool
    impact_scope: ToolImpactScope = ToolImpactScope.NONE
    reversibility: ToolReversibility = ToolReversibility.NOT_APPLICABLE
    confirmation: ToolConfirmation = ToolConfirmation.NONE
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
        list_filter_facets search_questions search_questions_compact search_questions_curated search_method_questions download_question_images search_topic_questions
        get_questions_by_ids list_knowledge_tree search_knowledge_points get_question_knowledge_points
        list_question_tags list_method_retrieval_feedback method_retrieval_learning_report database_boundary_report
        database_health_report find_similar_questions scan_canonical_duplicate_questions list_canonical_duplicate_merges
        get_workflow_guide mcp_system_health
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

def _write_policy(
    risk: ToolRisk,
    scope: ToolImpactScope,
    reversibility: ToolReversibility,
    confirmation: ToolConfirmation,
) -> tuple[ToolRisk, ToolImpactScope, ToolReversibility, ToolConfirmation]:
    return risk, scope, reversibility, confirmation


# Explicit declaration for every tool that can mutate durable state or create
# files.  Everything not listed here is read-only.  This avoids guessing risk
# from a verb prefix (for example, a report tool is read-only even if its name
# does not begin with ``get_``).
_WRITE_POLICIES = {
    # Search/cache
    "download_question_images": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.DOWNLOAD_CACHE, ToolReversibility.REGENERABLE, ToolConfirmation.DIRECT),
    # Canonical metadata and controlled canonical workflows
    "create_knowledge_points": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DIRECT),
    "organize_knowledge_tree": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DIRECT),
    "batch_update_question_metadata": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DRY_RUN),
    "maintain_question_tags": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DRY_RUN),
    "record_method_retrieval_feedback": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DIRECT),
    "maintain_question_knowledge_points": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DRY_RUN),
    "backfill_canonical_question_hashes": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DRY_RUN),
    "merge_canonical_duplicate_questions": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_CONTROLLED, ToolReversibility.SOFT_DELETE, ToolConfirmation.PLAN_TOKEN),
    "restore_canonical_duplicate_merge": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_CONTROLLED, ToolReversibility.AUDITED, ToolConfirmation.PLAN_TOKEN),
    "batch_replace_question_tags": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DRY_RUN),
    "batch_replace_question_knowledge_points": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DRY_RUN),
    "return_question_to_review": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_CONTROLLED, ToolReversibility.AUDITED, ToolConfirmation.PLAN_TOKEN),
    "reconcile_review_queue_outbox": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.AUDITED, ToolConfirmation.DIRECT),
    "rollback_change_batch": _write_policy(ToolRisk.HIGH, ToolImpactScope.CANONICAL_CONTROLLED, ToolReversibility.AUDITED, ToolConfirmation.PLAN_TOKEN),
    # Review workspace
    "import_word_folder_to_review": _write_policy(ToolRisk.HIGH, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.LIMITED, ToolConfirmation.DRY_RUN),
    "delete_review_tasks": _write_policy(ToolRisk.HIGH, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.LIMITED, ToolConfirmation.EXPLICIT),
    "clean_review_task_latex": _write_policy(ToolRisk.HIGH, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "split_merged_options": _write_policy(ToolRisk.HIGH, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "deduplicate_review_task_questions": _write_policy(ToolRisk.HIGH, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "update_review_task_draft": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "submit_ai_generated_review": _write_policy(ToolRisk.HIGH, ToolImpactScope.REVIEW_WORKSPACE, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    # Teaching projects and classroom sessions
    "duplicate_teaching_project": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.TEACHING_PROJECT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "publish_teaching_artifact": _write_policy(ToolRisk.HIGH, ToolImpactScope.TEACHING_PROJECT, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "sync_teaching_slides": _write_policy(ToolRisk.HIGH, ToolImpactScope.TEACHING_PROJECT, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "start_classroom_session": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CLASSROOM_SESSION, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    "update_classroom_session": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CLASSROOM_SESSION, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    "end_classroom_session": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CLASSROOM_SESSION, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    # Composition workbench (draft-only and version-conflict protected)
    "create_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "add_questions_to_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "add_knowledge_to_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "insert_teaching_block_to_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "reorder_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "move_composition_item": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "remove_items_from_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "update_composition_item": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "lock_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "apply_composition_workbench_plan": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DRY_RUN),
    "curate_questions_to_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    # Saved handouts, export configuration and files
    "export_composition_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.EXPORT_FILES, ToolReversibility.REGENERABLE, ToolConfirmation.DIRECT),
    "save_word_export_template": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.SAVED_HANDOUT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "rename_word_export_template": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.SAVED_HANDOUT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "restore_saved_handout_version": _write_policy(ToolRisk.HIGH, ToolImpactScope.SAVED_HANDOUT, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "rename_saved_handout": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.SAVED_HANDOUT, ToolReversibility.VERSIONED, ToolConfirmation.DIRECT),
    "apply_word_format_to_saved_handout": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.SAVED_HANDOUT, ToolReversibility.VERSIONED, ToolConfirmation.PLAN_TOKEN),
    "apply_word_format_to_workbench": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.WORKBENCH_DRAFT, ToolReversibility.VERSIONED, ToolConfirmation.DRY_RUN),
    "export_saved_handout": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.EXPORT_FILES, ToolReversibility.REGENERABLE, ToolConfirmation.DIRECT),
    "create_paper": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DIRECT),
    "associate_questions_to_paper": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.CANONICAL_METADATA, ToolReversibility.AUDITED, ToolConfirmation.DIRECT),
    "export_questions_to_typst": _write_policy(ToolRisk.MEDIUM, ToolImpactScope.EXPORT_FILES, ToolReversibility.REGENERABLE, ToolConfirmation.DRY_RUN),
    # Background jobs
    "submit_import_job": _write_policy(ToolRisk.HIGH, ToolImpactScope.TASK_QUEUE, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    "submit_ai_clean_job": _write_policy(ToolRisk.HIGH, ToolImpactScope.TASK_QUEUE, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    "submit_word_export_job": _write_policy(ToolRisk.HIGH, ToolImpactScope.TASK_QUEUE, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    "submit_pptx_export_job": _write_policy(ToolRisk.HIGH, ToolImpactScope.TASK_QUEUE, ToolReversibility.LIMITED, ToolConfirmation.DIRECT),
    "retry_job": _write_policy(ToolRisk.HIGH, ToolImpactScope.TASK_QUEUE, ToolReversibility.LIMITED, ToolConfirmation.EXPLICIT),
    "cancel_job": _write_policy(ToolRisk.HIGH, ToolImpactScope.TASK_QUEUE, ToolReversibility.LIMITED, ToolConfirmation.EXPLICIT),
}


def default_tool_registry() -> ToolRegistry:
    declarations: list[ToolSpec] = []
    for domain, names in _DOMAIN_TOOL_NAMES.items():
        for name in names:
            policy = _WRITE_POLICIES.get(name)
            if policy is None:
                declarations.append(
                    ToolSpec(name=name, domain=domain, risk=ToolRisk.LOW, read_only=True)
                )
                continue
            risk, scope, reversibility, confirmation = policy
            declarations.append(
                ToolSpec(
                    name=name,
                    domain=domain,
                    risk=risk,
                    read_only=False,
                    impact_scope=scope,
                    reversibility=reversibility,
                    confirmation=confirmation,
                )
            )
    unknown_policies = sorted(set(_WRITE_POLICIES) - {name for names in _DOMAIN_TOOL_NAMES.values() for name in names})
    if unknown_policies:
        raise RuntimeError(f"Tool policies reference undeclared tools: {', '.join(unknown_policies)}")
    return ToolRegistry(declarations)


def tool_policy_manifest() -> list[dict[str, Any]]:
    """Return the machine-readable impact policy for every public tool."""
    return [
        {
            "name": spec.name,
            "domain": spec.domain.value,
            "risk": spec.risk.value,
            "read_only": spec.read_only,
            "impact_scope": spec.impact_scope.value,
            "reversibility": spec.reversibility.value,
            "confirmation": spec.confirmation.value,
        }
        for spec in default_tool_registry().discover()
    ]


def discover_tools(
    *,
    domain: ToolDomain | str | None = None,
    risk: ToolRisk | str | None = None,
    writable: bool | None = None,
) -> tuple[ToolSpec, ...]:
    """Discover declared tools without importing the MCP transport runtime."""
    return default_tool_registry().discover(domain=domain, risk=risk, writable=writable)


def profile_tool_names(profile: str) -> frozenset[str]:
    """Return the allowed MCP tools for a named client capability profile."""
    normalized = profile.strip().lower()
    if normalized == "all":
        return default_tool_registry().names()
    if normalized == "ai_assistant_workbench":
        # The in-product assistant owns the composition workflow: it needs
        # retrieval tools to select questions and authoring tools to build a
        # workbench draft.
        return frozenset(_DOMAIN_TOOL_NAMES[ToolDomain.SEARCH] + _DOMAIN_TOOL_NAMES[ToolDomain.AUTHORING])
    if normalized == "external_study_sheet":
        # External clients may search and export selected canonical questions
        # to Typst, but never see composition-workbench mutation tools.
        return frozenset(_DOMAIN_TOOL_NAMES[ToolDomain.SEARCH] + ("export_questions_to_typst",))
    if normalized == "external_catalog_maintenance":
        # External clients may curate canonical metadata, but never access
        # authoring or composition-workbench tools.
        return frozenset(_DOMAIN_TOOL_NAMES[ToolDomain.SEARCH] + _DOMAIN_TOOL_NAMES[ToolDomain.MANAGEMENT])
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
    "ToolImpactScope",
    "ToolConfirmation",
    "ToolRegistry",
    "ToolReversibility",
    "ToolRisk",
    "ToolSpec",
    "default_tool_registry",
    "discover_tools",
    "profile_tool_names",
    "tool_policy_manifest",
]
