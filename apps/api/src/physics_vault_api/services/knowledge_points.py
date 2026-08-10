from __future__ import annotations

from ..repositories.knowledge_points import KnowledgePointRepository
from ..schemas.knowledge_points import KnowledgePointItem, QuestionKnowledgePointBatchItem, QuestionKnowledgePointLink, QuestionKnowledgePointUpsert


class KnowledgePointService:
    def __init__(self, repository: KnowledgePointRepository) -> None:
        self._repository = repository

    def question_counts_by_topic3(self) -> dict[str, int]:
        return self._repository.question_counts_by_topic3()

    def list(
        self,
        *,
        topic1_id: str | None,
        topic1_name: str | None,
        topic2_id: str | None,
        topic2_name: str | None,
        query: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[KnowledgePointItem]:
        return self._repository.list(
            topic1_id=topic1_id,
            topic1_name=topic1_name,
            topic2_id=topic2_id,
            topic2_name=topic2_name,
            query=query,
            status=status,
            limit=limit,
            offset=offset,
        )

    def list_for_question(self, question_id: str) -> list[QuestionKnowledgePointLink] | None:
        return self._repository.list_for_question(question_id)

    def replace_for_question(self, question_id: str, items: list[QuestionKnowledgePointBatchItem]) -> list[QuestionKnowledgePointLink] | None:
        if not items:
            raise ValueError("At least one knowledge point is required")
        if len(items) > 3:
            raise ValueError("A question can have at most 3 knowledge points")
        ranks = [item.rank for item in items]
        if len(set(ranks)) != len(ranks):
            raise ValueError("Duplicate ranks are not allowed")
        if 1 not in ranks:
            raise ValueError("rank=1 is required as the primary topic")
        if len({item.topic3_id for item in items}) != len(items):
            raise ValueError("Duplicate topic3_id values are not allowed")
        return self._repository.replace_for_question(question_id, items)

    def upsert_for_question(self, question_id: str, rank: int, item: QuestionKnowledgePointUpsert) -> QuestionKnowledgePointLink | None:
        if rank not in {1, 2, 3}:
            raise ValueError("rank must be 1, 2, or 3")
        return self._repository.upsert_for_question(question_id, rank, item)

    def delete_for_question(self, question_id: str, rank: int) -> None:
        if rank not in {1, 2, 3}:
            raise ValueError("rank must be 1, 2, or 3")
        if rank == 1:
            raise ValueError("rank=1 is the primary topic and should not be deleted")
        self._repository.delete_for_question(question_id, rank)
