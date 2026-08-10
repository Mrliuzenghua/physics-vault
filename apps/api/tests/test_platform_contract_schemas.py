from __future__ import annotations

from fastapi.routing import APIRoute

from physics_vault_api.routers.lesson_documents import build_lesson_documents_router
from physics_vault_api.routers.lesson_reflections import build_lesson_reflections_router
from physics_vault_api.routers.teaching_projects import build_teaching_projects_router
from physics_vault_api.schemas.lesson_documents import SavedHandoutResponse
from physics_vault_api.schemas.lesson_reflections import LessonReflectionResponse
from physics_vault_api.schemas.teaching_projects import TeachingProjectResponse


def _api_routes(router: object) -> list[APIRoute]:
    return [route for route in getattr(router, "routes", []) if isinstance(route, APIRoute)]


def test_teaching_lesson_and_handout_routes_publish_response_models() -> None:
    routers = [
        build_teaching_projects_router(),
        build_lesson_reflections_router(),
        build_lesson_documents_router(),
    ]

    for router in routers:
        routes = _api_routes(router)
        assert routes
        assert all(route.response_model is not None for route in routes)


def test_response_models_preserve_existing_document_extensions() -> None:
    project = TeachingProjectResponse.model_validate({
        "document_kind": "teaching_project",
        "id": "project-1",
        "content": {"nodes": []},
        "handout": {"id": "handout-1"},
        "slides": {"id": "slides-1"},
        "projectSnapshot": {"id": "project-1"},
    })
    handout = SavedHandoutResponse.model_validate({
        "document_kind": "saved_handout",
        "id": "handout-1",
        "lessonPackage": {"id": "handout-1"},
        "versions": [{"version": 1}],
        "extension": "preserved",
    })
    reflection = LessonReflectionResponse.model_validate({
        "document_kind": "lesson_reflection",
        "reflection": {"id": "reflection-1", "projectId": "project-1", "futureField": True},
    })

    assert project.model_dump()["projectSnapshot"] == {"id": "project-1"}
    assert handout.model_dump()["extension"] == "preserved"
    assert reflection.reflection.model_dump()["futureField"] is True
