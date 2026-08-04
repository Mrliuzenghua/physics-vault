from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from physics_vault_api.services import pdf_page_ocr
from physics_vault_api.services.pdf_page_ocr import _normalize_page_questions, parse_pdf_by_page


class FakeGateway:
    async def parse_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        page_name = Path(payload["file_path"]).stem
        if page_name.endswith("0002"):
            raise RuntimeError("ocr timeout")
        return {
            "questions": [
                {
                    "question_id": f"tmp_{page_name}",
                    "question_type": "calculation",
                    "title": f"title from {page_name}",
                    "options": [],
                    "answer": "",
                    "analysis": "",
                }
            ],
            "raw_text": f"text from {page_name}",
        }


@pytest.mark.anyio
async def test_parse_pdf_by_page_keeps_failed_page_isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pages = [(1, tmp_path / "page_0001.png"), (2, tmp_path / "page_0002.png"), (3, tmp_path / "page_0003.png")]
    for _, path in pages:
        path.write_bytes(b"fake")

    monkeypatch.setattr(pdf_page_ocr, "render_pdf_pages", lambda **_: pages)

    result = await parse_pdf_by_page(
        gateway=FakeGateway(),
        batch_id="batch-001",
        pdf_path=tmp_path / "source.pdf",
        output_dir=tmp_path / "pages",
        concurrency=2,
    )

    assert result["status"] == "partial_failed"
    assert result["page_count"] == 3
    assert result["question_count"] == 2
    assert [q["source_page"] for q in result["questions"]] == [1, 3]
    assert len(result["warnings"]) == 1


def test_normalize_page_questions_tolerates_ai_page_and_option_variants() -> None:
    questions = _normalize_page_questions(
        [
            {
                "question_id": "",
                "question_type": "填空题",
                "title": "测试题",
                "options": ["A. 选项一", "B. 选项二"],
                "source_page": "文件名而不是页码",
            }
        ],
        batch_id="batch-001",
        source="source.pdf",
        page_no=5,
    )

    assert questions[0]["question_type"] == "fill"
    assert questions[0]["source_page"] == 5
    assert questions[0]["options"] == [
        {"opt": "A", "content": "选项一"},
        {"opt": "B", "content": "选项二"},
    ]


def test_normalize_page_questions_keeps_region_bbox_for_review_linkage() -> None:
    questions = _normalize_page_questions(
        [
            {
                "question_id": "q-1",
                "title": "region question",
                "source_region_id": "region-1",
                "bbox": [100, 200, 900, 1200],
            }
        ],
        batch_id="batch-001",
        source="source.pdf",
        page_no=2,
    )

    assert questions[0]["source_region_id"] == "region-1"
    assert questions[0]["source_bbox"] == [100.0, 200.0, 800.0, 1000.0]
