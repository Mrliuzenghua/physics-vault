from __future__ import annotations

from ..repositories.processing_runs import ProcessingRunRepository
from ..schemas.processing_runs import ProcessingRunItem


class ProcessingRunService:
    """Business boundary for the read-only legacy processing-run history."""

    def __init__(self, repository: ProcessingRunRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        pipeline_name: str | None,
        paper_id: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[ProcessingRunItem]:
        return [
            ProcessingRunItem.model_validate(item)
            for item in self._repository.list(
                pipeline_name=pipeline_name,
                paper_id=paper_id,
                status=status,
                limit=limit,
                offset=offset,
            )
        ]
