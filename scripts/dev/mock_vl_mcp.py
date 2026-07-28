from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _response(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "1.0",
        "request_id": "mock-vl",
        "task_id": task_id,
        "success": True,
        "warnings": [],
        "errors": [],
        "result": result,
    }


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw or "{}")
    task_id = payload.get("task_id", "mock-task")
    request_payload = payload.get("payload", {})

    if "document" in request_payload:
        file_path = request_payload["document"].get("file_path", "")
        file_name = Path(file_path).name or "mock.pdf"
        result = {
            "document_type": "image_document",
            "pages": [
                {
                    "page_no": 1,
                    "image_path": file_path,
                    "question_regions": [
                        {
                            "region_id": "region_001",
                            "bbox": [60, 80, 980, 520],
                            "preview_path": f"./data/cache/{file_name}.region_001.png",
                            "status": "parsed",
                        }
                    ],
                }
            ],
            "questions": [
                {
                    "question_id": "tmp_q_001",
                    "question_type": "calculation",
                    "title": "已知小球沿斜面下滑，求到达底端时的速度。",
                    "options": [],
                    "answer": "",
                    "analysis": "",
                    "difficulty": 3,
                    "knowledge_point": "力学/机械能守恒/斜面模型",
                    "tags": ["斜面", "机械能守恒"],
                    "source": "mock",
                    "import_batch_id": task_id,
                    "source_page": 1,
                    "source_region_id": "region_001",
                    "raw_text": "mock vl result",
                    "confidence": 0.98,
                }
            ],
        }
    elif "page_image" in request_payload:
        result = {
            "page_no": 1,
            "regions": [{"region_id": "region_001", "bbox": [60, 80, 980, 520], "region_type": "question"}],
        }
    else:
        result = {
            "question": {
                "question_id": "tmp_q_region_001",
                "question_type": "single_choice",
                "title": "物体做自由落体运动时，下列说法正确的是（ ）。",
                "options": [
                    {"opt": "A", "content": "速度保持不变"},
                    {"opt": "B", "content": "加速度方向竖直向下"},
                ],
                "answer": "B",
                "analysis": "",
                "difficulty": 2,
                "knowledge_point": "力学/自由落体运动",
                "tags": ["自由落体"],
                "source": "mock",
                "import_batch_id": task_id,
                "source_page": 1,
                "source_region_id": request_payload.get("region", {}).get("region_id", "region_001"),
                "raw_text": "mock region parse",
                "confidence": 0.97,
            }
        }

    sys.stdout.write(json.dumps(_response(task_id, result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
