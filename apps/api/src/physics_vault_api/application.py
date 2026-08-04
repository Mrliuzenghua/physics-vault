from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import APIRouter

from .config import McpSettings, TaskQueueSettings
from .paths import default_review_db_path
from .repositories.import_tasks import SQLiteImportTaskRepository
from .repositories.knowledge_cache import KnowledgeCacheRepository
from .repositories.question_search import QuestionSearchRepository
from .repositories.question_write import QuestionWriteRepository
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
from .routers.favorites import build_favorites_router
from .routers.image_management import build_image_management_router
from .routers.import_pipeline import build_import_pipeline_router
from .routers.lesson_exports import build_lesson_exports_router
from .routers.mcp import build_mcp_router
from .routers.metadata_batch import build_metadata_batch_router
from .routers.mistake import build_mistake_router
from .routers.paper_drafts import build_paper_drafts_router
from .routers.question_search import build_question_search_router
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
from .services.mcp_gateway import McpGatewayService
from .services.lesson_exports import LessonExportService
from .services.metadata_batch import MetadataBatchService
from .services.mistake_service import MistakeService
from .services.paper_drafts import PaperDraftService
from .services.question_search import QuestionSearchService
from .services.question_variants import QuestionVariantService
from .services.question_write import QuestionWriteService
from .services.review_save import ReviewSaveService
from .services.similar_questions import SimilarQuestionsService
from .services.task_center import TaskCenterService


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
            import_pipeline_service=ImportPipelineService(
                task_repo=task_repo,
                pandoc=PandocAdapter(),
                cleaner=DocumentCleaningService(),
                parser=StructuredQuestionParsingService(),
                document_parser=gateway.document_parser,
                mcp_gateway=gateway,
            ),
            import_task_repo=task_repo,
            task_queue_settings=queue_settings,
        )


@dataclass(slots=True)
class ApplicationContainer:
    """Application composition root for repositories, services, and routers."""

    mcp_gateway: McpGatewayService
    question_search_repo: QuestionSearchRepository
    question_write_repo: QuestionWriteRepository
    knowledge_cache_repo: KnowledgeCacheRepository
    review_queue_repo: ReviewQueueRepository
    review_draft_repo: SQLiteReviewDraftRepository
    import_pipeline_service: ImportPipelineService
    lesson_export_service: LessonExportService
    question_search_service: QuestionSearchService
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

    @classmethod
    def build(cls, mcp_settings: McpSettings | None = None) -> "ApplicationContainer":
        settings = mcp_settings or McpSettings.from_env()
        mcp_gateway = McpGatewayService(settings)
        if _should_restore_runtime_ai_config(settings, explicit_settings=mcp_settings is not None):
            mcp_gateway.notify_config_updated(get_runtime_config())

        question_search_repo = QuestionSearchRepository()
        question_write_repo = QuestionWriteRepository()
        knowledge_cache_repo = KnowledgeCacheRepository()
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

        return cls(
            mcp_gateway=mcp_gateway,
            question_search_repo=question_search_repo,
            question_write_repo=question_write_repo,
            knowledge_cache_repo=knowledge_cache_repo,
            review_queue_repo=review_queue_repo,
            review_draft_repo=review_draft_repo,
            import_pipeline_service=ImportPipelineService(
                task_repo=task_repo,
                pandoc=PandocAdapter(),
                cleaner=DocumentCleaningService(),
                parser=StructuredQuestionParsingService(),
                document_parser=mcp_gateway.document_parser,
                mcp_gateway=mcp_gateway,
            ),
            lesson_export_service=LessonExportService(task_repo),
            question_search_service=question_search_service,
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
        )

    def routers(self) -> Iterable[APIRouter]:
        yield build_import_pipeline_router(self.import_pipeline_service, draft_repository=self.review_draft_repo)
        yield build_lesson_exports_router(self.lesson_export_service)
        yield build_tasks_router(TaskCenterService(self.import_pipeline_service, lesson_export_service=self.lesson_export_service))
        yield build_mcp_router(self.mcp_gateway)
        yield build_question_search_router(self.question_search_service, self.question_write_service)
        yield build_review_queue_router(self.review_queue_repo)
        yield build_review_save_router(self.review_save_service, self.review_draft_repo)
        yield build_ai_assistant_router(self.ai_assistant_service)
        yield build_agents_router(self.claude_code_agent_service)
        yield build_ai_generation_router(self.ai_generation_service)
        yield build_annotation_router()
        yield build_analysis_batch_router(self.analysis_batch_service)
        yield build_assets_manager_router(self.assets_manager_service)
        yield build_question_variants_router(self.question_variant_service)
        yield build_similar_questions_router(self.similar_questions_service)
        yield build_collections_router()
        yield build_favorites_router()
        yield build_image_management_router()
        yield build_export_package_router()
        yield build_restore_package_router()
        yield build_system_status_router(self.question_search_repo)
        yield build_mistake_router(self.mistake_service)
        yield build_metadata_batch_router(self.metadata_batch_service)
        yield build_paper_drafts_router(self.paper_draft_service)
        yield build_change_audit_router(self.change_audit_service)


def _should_restore_runtime_ai_config(settings: McpSettings, *, explicit_settings: bool) -> bool:
    if os.getenv("PHYSICS_RESTORE_RUNTIME_AI_CONFIG", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if explicit_settings or not settings.enabled:
        return False
    if os.getenv("PHYSICS_MCP_MODE"):
        return settings.mode == "http"
    return True
