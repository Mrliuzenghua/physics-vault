from __future__ import annotations

from ..repositories.embedding_status import EmbeddingStatusRepository
from ..schemas.embedding_status import EmbeddingStatusItem


class EmbeddingStatusService:
    def __init__(self, repository: EmbeddingStatusRepository) -> None:
        self._repository = repository

    def list_question_embeddings(self) -> list[EmbeddingStatusItem]:
        return self._repository.list_question_embeddings()
