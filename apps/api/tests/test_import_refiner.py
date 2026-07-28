from __future__ import annotations

from typing import Any

from physics_vault_api.services.import_refiner import refine_import_questions_concurrent


def test_refine_import_questions_keeps_failed_batch_local() -> None:
    questions = [
        {
            "question_id": f"q{i}",
            "question_type": "calculation",
            "title": f"local {i}",
            "options": [],
            "answer": "",
            "analysis": "",
        }
        for i in range(4)
    ]

    def fake_call(messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        content = messages[-1]["content"]
        if "q2" in content:
            raise RuntimeError("model timeout")
        return {
            "questions": [
                {
                    "question_id": "q0",
                    "question_type": "single_choice",
                    "title": "refined 0",
                    "options": [{"opt": "A", "content": "option"}],
                    "answer": "A",
                    "analysis": "ok",
                },
                {
                    "question_id": "q1",
                    "question_type": "calculation",
                    "title": "refined 1",
                    "options": [],
                    "answer": "1",
                    "analysis": "ok",
                },
            ]
        }

    result = refine_import_questions_concurrent(
        questions=questions,
        call=fake_call,
        batch_size=2,
        max_workers=2,
        time_budget_seconds=10,
    )

    refined = result["questions"]
    assert result["refined_count"] == 2
    assert refined[0]["title"] == "refined 0"
    assert refined[1]["title"] == "refined 1"
    assert refined[2]["title"] == "local 2"
    assert refined[3]["title"] == "local 3"
