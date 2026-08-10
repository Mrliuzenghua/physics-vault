from __future__ import annotations

import sys
import warnings
from dataclasses import fields

from physics_vault_api.app import create_app
from physics_vault_api.application import ApplicationContainer, ExportWorkerContainer, WorkerContainer
from physics_vault_api.config import McpSettings
from physics_vault_api.main import create_app as create_main_app


EXPECTED_APPLICATION_ROUTER_MANIFEST = (
    "home",
    "import_pipeline",
    "lesson_exports",
    "lesson_documents",
    "lesson_reflections",
    "mcp_lesson_reflections",
    "teaching_projects",
    "mcp_teaching_projects",
    "tasks",
    "mcp",
    "image_catalog",
    "embedding_status",
    "embedding_builds",
    "papers",
    "question_search",
    "question_reviews",
    "question_imports",
    "question_details",
    "question_stats",
    "question_versions",
    "question_updates",
    "processing_runs",
    "knowledge_points",
    "review_queue",
    "review_save",
    "ai_assistant",
    "agents",
    "ai_generation",
    "annotation",
    "analysis_batch",
    "assets_manager",
    "question_variants",
    "similar_questions",
    "collections",
    "favorites",
    "image_management",
    "export_package",
    "restore_package",
    "system_status",
    "mistake",
    "metadata_batch",
    "paper_drafts",
    "change_audit",
)


def _route_method_keys(route: object) -> set[tuple[str, str]]:
    nested_router = getattr(route, "original_router", None)
    nested_routes = getattr(nested_router, "routes", ())
    if nested_routes:
        return {
            key
            for nested_route in nested_routes
            for key in _route_method_keys(nested_route)
        }
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None) or ()
    return set() if not path else {(path, method) for method in methods}


def test_main_uses_the_single_application_factory() -> None:
    assert create_main_app is create_app


def test_application_startup_does_not_load_legacy_app() -> None:
    assert "physics_vault_api.legacy_app" not in sys.modules


def test_application_container_assembly_manifest_covers_every_member_once() -> None:
    manifest_members = tuple(
        member
        for group in ApplicationContainer.ASSEMBLY_MANIFEST
        for member in group.members
    )

    assert [group.name for group in ApplicationContainer.ASSEMBLY_MANIFEST] == [
        "mcp",
        "asset_and_embedding_storage",
        "question_storage",
        "knowledge_and_review_storage",
        "import_and_exports",
        "question_services",
        "platform_services",
    ]
    assert manifest_members == tuple(field.name for field in fields(ApplicationContainer))
    assert len(manifest_members) == len(set(manifest_members))


def test_application_router_manifest_is_ordered_and_named() -> None:
    container = ApplicationContainer.build(mcp_settings=McpSettings(enabled=False))
    manifest = list(container.router_manifest())
    names = tuple(name for name, _router in manifest)

    assert names == EXPECTED_APPLICATION_ROUTER_MANIFEST
    assert len(names) == len(set(names))
    assert all(router.routes for _name, router in manifest)
    assert container.task_center_service._import_service is container.import_pipeline_service
    assert container.task_center_service._lesson_export_service is container.lesson_export_service


def test_worker_containers_do_not_expose_web_router_assembly() -> None:
    for container_type in (WorkerContainer, ExportWorkerContainer):
        assert "routers" not in container_type.__dict__
        assert "router_manifest" not in container_type.__dict__
        assert all("router" not in field.name for field in fields(container_type))


def test_unified_app_has_no_duplicate_path_method_pairs() -> None:
    app = create_app()
    keys: list[tuple[str, str]] = []
    for route in app.routes:
        keys.extend(_route_method_keys(route))

    duplicates = {key for key in keys if keys.count(key) > 1}
    assert duplicates == set()


def test_unified_openapi_has_no_duplicate_operation_warning() -> None:
    app = create_app()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app.openapi()

    duplicate_warnings = [
        warning
        for warning in caught
        if "Duplicate Operation ID" in str(warning.message)
    ]
    assert duplicate_warnings == []
