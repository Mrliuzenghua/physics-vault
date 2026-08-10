from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from fastapi import APIRouter
from fastapi.routing import APIRoute

from .config import McpSettings, TaskQueueSettings
from .paths import default_review_db_path
from .repositories.import_tasks import SQLiteImportTaskRepository
from .repositories.image_catalog import ImageCatalogRepository
from .repositories.embedding_status import EmbeddingStatusRepository
from .repositories.knowledge_cache import KnowledgeCacheRepository
from .repositories.knowledge_points import KnowledgePointRepository
from .repositories.question_search import QuestionSearchRepository
from .repositories.question_reviews import QuestionReviewRepository
from .repositories.question_imports import QuestionImportRepository
from .repositories.question_details import QuestionDetailRepository
from .repositories.question_stats import QuestionStatsRepository
from .repositories.question_write import QuestionWriteRepository
from .repositories.processing_runs import ProcessingRunRepository
from .repositories.papers import PaperRepository
from .repositories.review_queue import ReviewQueueRepository
from .repositories.review_drafts import SQLiteReviewDraftRepository
from .routers.ai_assistant import build_ai_assistant_router
from .routers.ai_generation import build_ai_generation_router
from .routers.analysis_batch import build_analysis_batch_router
from .routers.annotations import build_annotation_router
from .routers.agents import build_agents_router
from .routers.assets_manager import build_assets_manager_router
from .routers.change_audit import build_change_audit_router
from .routers.collections import build_collections_router
from .routers.export_package import build_export_package_router
from .routers.home import build_home_router
from .routers.embedding_status import build_embedding_status_router
from .routers.embedding_builds import build_embedding_builds_router
from .routers.favorites import build_favorites_router
from .routers.image_management import build_image_management_router
from .routers.image_catalog import build_image_catalog_router
from .routers.import_pipeline import build_import_pipeline_router
from .routers.lesson_exports import build_lesson_exports_router
from .routers.lesson_documents import build_lesson_documents_router
from .routers.lesson_reflections import build_lesson_reflections_router, build_mcp_lesson_reflections_router
from .routers.knowledge_points import build_knowledge_points_router
from .routers.teaching_projects import build_mcp_teaching_projects_router, build_teaching_projects_router
from .routers.mcp import build_mcp_router
from .routers.metadata_batch import build_metadata_batch_router
from .routers.mistake import build_mistake_router
from .routers.paper_drafts import build_paper_drafts_router
from .routers.papers import build_papers_router
from .routers.processing_runs import build_processing_runs_router
from .routers.question_search import build_question_search_router
from .routers.question_reviews import build_question_reviews_router
from .routers.question_imports import build_question_imports_router
from .routers.question_details import build_question_details_router
from .routers.question_stats import build_question_stats_router
from .routers.question_versions import build_question_versions_router
from .routers.question_updates import build_question_updates_router
from .routers.question_variants import build_question_variants_router
from .routers.restore_package import build_restore_package_router
from .routers.review_queue import build_review_queue_router
from .routers.review_save import build_review_save_router
from .routers.system_status import build_system_status_router
from .routers.tasks import build_tasks_router
from .runtime_config import get_runtime_config
from .routers.similar_questions import build_similar_questions_router
from .services.ai_assistant import AiAssistantService
from .services.ai_generation import AiGenerationService
from .services.image_catalog import ImageCatalogService
from .services.analysis_batch import AnalysisBatchService
from .services.assets_manager import AssetsManagerService
from .services.change_audit import ChangeAuditService
from .services.claude_code_agent import ClaudeCodeAgentService
from .services.document_pipeline import (
    DocumentCleaningService,
    ImportPipelineService,
    PandocAdapter,
    StructuredQuestionParsingService,
)
from .services.embedding_status import EmbeddingStatusService
from .services.embedding_builds import EmbeddingBuildService
from .services.mcp_gateway import McpGatewayService
from .services.lesson_exports import LessonExportService
from .services.knowledge_points import KnowledgePointService
from .services.metadata_batch import MetadataBatchService
from .services.mistake_service import MistakeService
from .services.paper_drafts import PaperDraftService
from .services.papers import PaperService
from .services.processing_runs import ProcessingRunService
from .services.question_search import QuestionSearchService
from .services.question_reviews import QuestionReviewService
from .services.question_imports import QuestionImportService
from .services.question_details import QuestionDetailService
from .services.question_stats import QuestionStatsService
from .services.question_versions import QuestionVersionService
from .services.question_updates import QuestionUpdateService
from .services.question_variants import QuestionVariantService
from .services.question_write import QuestionWriteService
from .services.review_save import ReviewSaveService
from .services.similar_questions import SimilarQuestionsService
from .services.task_center import TaskCenterService


@dataclass(frozen=True, slots=True)
class AssemblyGroup:
    """A named set of container members that are built and shared together."""

    name: str
    members: tuple[str, ...]


def _build_import_pipeline_service(
    task_repo: SQLiteImportTaskRepository,
    mcp_gateway: McpGatewayService,
) -> ImportPipelineService:
    """Build the import pipeline shared by the Web process and task workers."""

    return ImportPipelineService(
        task_repo=task_repo,
        pandoc=PandocAdapter(),
        cleaner=DocumentCleaningService(),
        parser=StructuredQuestionParsingService(),
        document_parser=mcp_gateway.document_parser,
        mcp_gateway=mcp_gateway,
    )


def _build_api_compatibility_router(router: APIRouter) -> APIRouter | None:
    """Expose root-path compatibility routes under the canonical ``/api`` tree."""

    root_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path != "/" and not route.path.startswith("/api/")
    ]
    if not root_routes:
        return None

    canonical = APIRouter(prefix="/api")
    for route in root_routes:
        canonical.add_api_route(
            route.path,
            route.endpoint,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            methods=route.methods,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
            response_model_exclude_unset=route.response_model_exclude_unset,
            response_model_exclude_defaults=route.response_model_exclude_defaults,
            response_model_exclude_none=route.response_model_exclude_none,
            include_in_schema=route.include_in_schema,
            response_class=route.response_class,
            name=f"api_{route.name}",
            callbacks=route.callbacks,
            openapi_extra=route.openapi_extra,
            strict_content_type=route.strict_content_type,
        )
    return canonical


@dataclass(slots=True)
class ExportWorkerContainer:
    """Small worker composition root for snapshot-only Office exports."""

    lesson_export_service: LessonExportService
    import_task_repo: SQLiteImportTaskRepository

    @classmethod
    def build(cls, task_queue_settings: TaskQueueSettings | None = None) -> "ExportWorkerContainer":
        queue_settings = task_queue_settings or TaskQueueSettings.from_env()
        task_repo = SQLiteImportTaskRepository(str(default_review_db_path()))
        task_repo.recover_stale_tasks(queue_settings.stale_task_after_seconds)
        return cls(
            lesson_export_service=LessonExportService(task_repo),
            import_task_repo=task_repo,
        )


@dataclass(slots=True)
class WorkerContainer:
    """Minimal composition root for task workers; it excludes Web-only services."""

    import_pipeline_service: ImportPipelineService
    import_task_repo: SQLiteImportTaskRepository
    task_queue_settings: TaskQueueSettings

    @classmethod
    def build(
        cls,
        mcp_settings: McpSettings | None = None,
        task_queue_settings: TaskQueueSettings | None = None,
        *,
        recover_stale: bool = True,
    ) -> "WorkerContainer":
        settings = mcp_settings or McpSettings.from_env()
        queue_settings = task_queue_settings or TaskQueueSettings.from_env()
        gateway = McpGatewayService(settings)
        if _should_restore_runtime_ai_config(settings, explicit_settings=mcp_settings is not None):
            gateway.notify_config_updated(get_runtime_config())

        task_repo = SQLiteImportTaskRepository(str(default_review_db_path()))
        if recover_stale:
            task_repo.recover_stale_tasks(queue_settings.stale_task_after_seconds)
        return cls(
            import_pipeline_service=_build_import_pipeline_service(task_repo, gateway),
            import_task_repo=task_repo,
            task_queue_settings=queue_settings,
        )


@dataclass(slots=True)
class ApplicationContainer:
    """Application composition root for repositories, services, and routers."""

    ASSEMBLY_MANIFEST: ClassVar[tuple[AssemblyGroup, ...]] = (
        AssemblyGroup("mcp", ("mcp_gateway",)),
        AssemblyGroup("asset_and_embedding_storage", ("image_catalog_repo", "embedding_status_repo")),
        AssemblyGroup(
            "question_storage",
            (
                "question_search_repo",
                "question_review_repo",
                "question_import_repo",
                "question_detail_repo",
                "question_stats_repo",
                "question_write_repo",
                "processing_run_repo",
                "paper_repo",
            ),
        ),
        AssemblyGroup(
            "knowledge_and_review_storage",
            (
                "knowledge_cache_repo",
                "knowledge_point_repo",
                "review_queue_repo",
                "review_draft_repo",
            ),
        ),
        AssemblyGroup(
            "import_and_exports",
            ("import_pipeline_service", "lesson_export_service", "task_center_service"),
        ),
        AssemblyGroup(
            "question_services",
            (
                "question_search_service",
                "question_review_service",
                "question_import_service",
                "question_detail_service",
                "question_stats_service",
                "question_version_service",
                "question_update_service",
                "question_write_service",
                "review_save_service",
            ),
        ),
        AssemblyGroup(
            "platform_services",
            (
                "ai_generation_service",
                "question_variant_service",
                "analysis_batch_service",
                "assets_manager_service",
                "mistake_service",
                "metadata_batch_service",
                "similar_questions_service",
                "paper_draft_service",
                "ai_assistant_service",
                "claude_code_agent_service",
                "change_audit_service",
                "image_catalog_service",
                "embedding_status_service",
                "embedding_build_service",
                "processing_run_service",
                "knowledge_point_service",
                "paper_service",
            ),
        ),
    )

    mcp_gateway: McpGatewayService
    image_catalog_repo: ImageCatalogRepository
    embedding_status_repo: EmbeddingStatusRepository
    question_search_repo: QuestionSearchRepository
    question_review_repo: QuestionReviewRepository
    question_import_repo: QuestionImportRepository
    question_detail_repo: QuestionDetailRepository
    question_stats_repo: QuestionStatsRepository
    question_write_repo: QuestionWriteRepository
    processing_run_repo: ProcessingRunRepository
    paper_repo: PaperRepository
    knowledge_cache_repo: KnowledgeCacheRepository
    knowledge_point_repo: KnowledgePointRepository
    review_queue_repo: ReviewQueueRepository
    review_draft_repo: SQLiteReviewDraftRepository
    import_pipeline_service: ImportPipelineService
    lesson_export_service: LessonExportService
    task_center_service: TaskCenterService
    question_search_service: QuestionSearchService
    question_review_service: QuestionReviewService
    question_import_service: QuestionImportService
    question_detail_service: QuestionDetailService
    question_stats_service: QuestionStatsService
    question_version_service: QuestionVersionService
    question_update_service: QuestionUpdateService
    question_write_service: QuestionWriteService
    review_save_service: ReviewSaveService
    ai_generation_service: AiGenerationService
    question_variant_service: QuestionVariantService
    analysis_batch_service: AnalysisBatchService
    assets_manager_service: AssetsManagerService
    mistake_service: MistakeService
    metadata_batch_service: MetadataBatchService
    similar_questions_service: SimilarQuestionsService
    paper_draft_service: PaperDraftService
    ai_assistant_service: AiAssistantService
    claude_code_agent_service: ClaudeCodeAgentService
    change_audit_service: ChangeAuditService
    image_catalog_service: ImageCatalogService
    embedding_status_service: EmbeddingStatusService
    embedding_build_service: EmbeddingBuildService
    processing_run_service: ProcessingRunService
    knowledge_point_service: KnowledgePointService
    paper_service: PaperService

    @classmethod
    def build(cls, mcp_settings: McpSettings | None = None) -> "ApplicationContainer":
        settings = mcp_settings or McpSettings.from_env()
        mcp_gateway = McpGatewayService(settings)
        image_catalog_repo = ImageCatalogRepository()
        embedding_status_repo = EmbeddingStatusRepository()
        if _should_restore_runtime_ai_config(settings, explicit_settings=mcp_settings is not None):
            mcp_gateway.notify_config_updated(get_runtime_config())

        question_search_repo = QuestionSearchRepository()
        question_review_repo = QuestionReviewRepository()
        question_import_repo = QuestionImportRepository()
        question_detail_repo = QuestionDetailRepository()
        question_stats_repo = QuestionStatsRepository()
        question_write_repo = QuestionWriteRepository()
        processing_run_repo = ProcessingRunRepository()
        paper_repo = PaperRepository()
        knowledge_cache_repo = KnowledgeCacheRepository()
        knowledge_point_repo = KnowledgePointRepository()
        # Review data never auto-migrates from the canonical database at runtime.
        # Any legacy recovery must be a deliberate offline operation.
        review_queue_repo = ReviewQueueRepository(migrate_legacy=False)
        review_draft_repo = SQLiteReviewDraftRepository(str(default_review_db_path()))
        task_repo = SQLiteImportTaskRepository(str(default_review_db_path()))

        question_search_service = QuestionSearchService(question_search_repo)
        question_write_service = QuestionWriteService(question_write_repo)
        review_save_service = ReviewSaveService(question_write_service)
        ai_generation_service = AiGenerationService(mcp_gateway, knowledge_cache_repo)
        question_variant_service = QuestionVariantService(mcp_gateway)
        import_pipeline_service = _build_import_pipeline_service(task_repo, mcp_gateway)
        lesson_export_service = LessonExportService(task_repo)
        task_center_service = TaskCenterService(
            import_pipeline_service,
            lesson_export_service=lesson_export_service,
        )

        return cls(
            mcp_gateway=mcp_gateway,
            image_catalog_repo=image_catalog_repo,
            embedding_status_repo=embedding_status_repo,
            question_search_repo=question_search_repo,
            question_review_repo=question_review_repo,
            question_import_repo=question_import_repo,
            question_detail_repo=question_detail_repo,
            question_stats_repo=question_stats_repo,
            question_write_repo=question_write_repo,
            processing_run_repo=processing_run_repo,
            paper_repo=paper_repo,
            knowledge_cache_repo=knowledge_cache_repo,
            knowledge_point_repo=knowledge_point_repo,
            review_queue_repo=review_queue_repo,
            review_draft_repo=review_draft_repo,
            import_pipeline_service=import_pipeline_service,
            lesson_export_service=lesson_export_service,
            task_center_service=task_center_service,
            question_search_service=question_search_service,
            question_review_service=QuestionReviewService(question_review_repo, review_queue_repo),
            question_import_service=QuestionImportService(question_import_repo, review_queue_repo),
            question_detail_service=QuestionDetailService(question_detail_repo),
            question_stats_service=QuestionStatsService(question_stats_repo),
            question_version_service=QuestionVersionService(question_write_repo, question_write_service),
            question_update_service=QuestionUpdateService(question_detail_repo, question_write_service),
            question_write_service=question_write_service,
            review_save_service=review_save_service,
            ai_generation_service=ai_generation_service,
            question_variant_service=question_variant_service,
            analysis_batch_service=AnalysisBatchService(ai_generation_service),
            assets_manager_service=AssetsManagerService(),
            mistake_service=MistakeService(question_write_repo),
            metadata_batch_service=MetadataBatchService(question_write_repo, mcp_gateway),
            similar_questions_service=SimilarQuestionsService(),
            paper_draft_service=PaperDraftService(),
            ai_assistant_service=AiAssistantService(question_search_repo),
            claude_code_agent_service=ClaudeCodeAgentService(question_search_repo),
            change_audit_service=ChangeAuditService(),
            image_catalog_service=ImageCatalogService(image_catalog_repo),
            embedding_status_service=EmbeddingStatusService(embedding_status_repo),
            embedding_build_service=EmbeddingBuildService(),
            processing_run_service=ProcessingRunService(processing_run_repo),
            knowledge_point_service=KnowledgePointService(knowledge_point_repo),
            paper_service=PaperService(paper_repo),
        )

    def _base_router_manifest(self) -> Iterable[tuple[str, APIRouter]]:
        """Return the ordered Web router assembly manifest.

        Router factories belong here rather than in ``app.create_app`` so every
        Web entry point receives the same shared service instances.
        """

        yield "home", build_home_router()

        # Import and lesson delivery.
        yield "import_pipeline", build_import_pipeline_router(
            self.import_pipeline_service,
            draft_repository=self.review_draft_repo,
        )
        yield "lesson_exports", build_lesson_exports_router(self.lesson_export_service)
        yield "lesson_documents", build_lesson_documents_router()
        yield "lesson_reflections", build_lesson_reflections_router()
        yield "mcp_lesson_reflections", build_mcp_lesson_reflections_router()
        yield "teaching_projects", build_teaching_projects_router()
        yield "mcp_teaching_projects", build_mcp_teaching_projects_router()
        yield "tasks", build_tasks_router(self.task_center_service)

        # MCP, assets, and platform diagnostics.
        yield "mcp", build_mcp_router(self.mcp_gateway)
        yield "image_catalog", build_image_catalog_router(self.image_catalog_service)
        yield "embedding_status", build_embedding_status_router(self.embedding_status_service)
        yield "embedding_builds", build_embedding_builds_router(self.embedding_build_service)

        # Question and review workflows.
        yield "papers", build_papers_router(self.paper_service)
        yield "question_search", build_question_search_router(
            self.question_search_service,
            self.question_write_service,
        )
        yield "question_reviews", build_question_reviews_router(self.question_review_service)
        yield "question_imports", build_question_imports_router(self.question_import_service)
        yield "question_details", build_question_details_router(self.question_detail_service)
        yield "question_stats", build_question_stats_router(self.question_stats_service)
        yield "question_versions", build_question_versions_router(self.question_version_service)
        yield "question_updates", build_question_updates_router(self.question_update_service)
        yield "processing_runs", build_processing_runs_router(self.processing_run_service)
        yield "knowledge_points", build_knowledge_points_router(self.knowledge_point_service)
        yield "review_queue", build_review_queue_router(self.review_queue_repo)
        yield "review_save", build_review_save_router(self.review_save_service, self.review_draft_repo)

        # Assisted authoring and package management.
        yield "ai_assistant", build_ai_assistant_router(self.ai_assistant_service)
        yield "agents", build_agents_router(self.claude_code_agent_service)
        yield "ai_generation", build_ai_generation_router(self.ai_generation_service)
        yield "annotation", build_annotation_router()
        yield "analysis_batch", build_analysis_batch_router(self.analysis_batch_service)
        yield "assets_manager", build_assets_manager_router(self.assets_manager_service)
        yield "question_variants", build_question_variants_router(self.question_variant_service)
        yield "similar_questions", build_similar_questions_router(self.similar_questions_service)
        yield "collections", build_collections_router()
        yield "favorites", build_favorites_router()
        yield "image_management", build_image_management_router()
        yield "export_package", build_export_package_router()
        yield "restore_package", build_restore_package_router()
        yield "system_status", build_system_status_router(self.question_search_repo)
        yield "mistake", build_mistake_router(self.mistake_service)
        yield "metadata_batch", build_metadata_batch_router(self.metadata_batch_service)
        yield "paper_drafts", build_paper_drafts_router(self.paper_draft_service)
        yield "change_audit", build_change_audit_router(self.change_audit_service)

    def router_manifest(self) -> Iterable[tuple[str, APIRouter]]:
        """Return legacy routes plus their canonical ``/api`` compatibility aliases."""

        for name, router in self._base_router_manifest():
            yield name, router
            if compatibility_router := _build_api_compatibility_router(router):
                yield f"{name}_api_compat", compatibility_router

    def routers(self) -> Iterable[APIRouter]:
        """Expose only router instances to FastAPI while retaining manifest labels."""

        for _name, router in self.router_manifest():
            yield router


def _should_restore_runtime_ai_config(settings: McpSettings, *, explicit_settings: bool) -> bool:
    if os.getenv("PHYSICS_RESTORE_RUNTIME_AI_CONFIG", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if explicit_settings or not settings.enabled:
        return False
    if os.getenv("PHYSICS_MCP_MODE"):
        return settings.mode == "http"
    return True
