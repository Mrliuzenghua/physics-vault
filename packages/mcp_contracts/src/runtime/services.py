"""Service factory used by the MCP composition root.

Imports are intentionally local: the contracts package is also consumed by
the API application, so eagerly importing application services here would
create an avoidable import cycle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MCPServiceFactory:
    """Create MCP-facing application services with the configured DB boundary."""

    formal_db_path: Callable[[], Path]
    review_db_path: Callable[[], Path]

    def search(self) -> Any:
        from physics_vault_api.services.question_search import QuestionSearchService

        return QuestionSearchService()

    def import_pipeline(self) -> Any:
        from physics_vault_api.repositories.import_tasks import SQLiteImportTaskRepository
        from physics_vault_api.services.document_pipeline import (
            DocumentCleaningService,
            ImportPipelineService,
            PandocAdapter,
            StructuredQuestionParsingService,
        )

        return ImportPipelineService(
            task_repo=SQLiteImportTaskRepository(str(self.review_db_path())),
            pandoc=PandocAdapter(),
            cleaner=DocumentCleaningService(),
            parser=StructuredQuestionParsingService(),
        )

    def task_center(self) -> Any:
        from physics_vault_api.services.lesson_exports import LessonExportService
        from physics_vault_api.services.task_center import TaskCenterService

        import_service = self.import_pipeline()
        return TaskCenterService(
            import_service,
            lesson_export_service=LessonExportService(import_service._task_repo),
        )

    def typst_export(self) -> Any:
        from physics_vault_api.services.typst_exports import TypstQuestionExportService

        return TypstQuestionExportService(db_path=self.formal_db_path())

    def paper_draft(self) -> Any:
        from physics_vault_api.services.paper_drafts import PaperDraftService

        return PaperDraftService()

    def change_audit(self) -> Any:
        from physics_vault_api.services.change_audit import ChangeAuditService

        return ChangeAuditService(
            db_path=self.formal_db_path(),
            review_db_path=self.review_db_path(),
        )

    def metadata_management(self) -> Any:
        from physics_vault_api.services.metadata_management import MetadataManagementService

        return MetadataManagementService(self.formal_db_path())
