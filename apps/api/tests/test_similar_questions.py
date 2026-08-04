from typing import Any

from physics_vault_api.services.similar_questions import SimilarQuestionsService


class _QuestionRepository:
    def __init__(self) -> None:
        self.requested_ids: list[str] = []

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        self.requested_ids = question_ids
        return [{"question_id": question_ids[0], "canonical_title": "target"}]


def test_source_question_is_loaded_directly_by_id() -> None:
    repository = _QuestionRepository()
    service = SimilarQuestionsService(repository)  # type: ignore[arg-type]

    question = service._get_question("q-250")

    assert repository.requested_ids == ["q-250"]
    assert question == {"question_id": "q-250", "canonical_title": "target"}
