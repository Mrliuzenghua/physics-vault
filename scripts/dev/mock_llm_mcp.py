from __future__ import annotations

import json
import sys


def _response(task_id: str, result: dict[str, object]) -> dict[str, object]:
    return {
        "version": "1.0",
        "request_id": "mock-llm",
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

    if "knowledge_points" in request_payload:
        result = {
            "knowledge_key": "mock_knowledge_key",
            "title": "专题知识点总结",
            "content": "先建立物理情境，再判断受力与运动关系，最后选择对应规律求解。",
            "outline": ["情境识别", "规律选择", "规范表达"],
        }
    elif "questions" in request_payload:
        items = []
        for item in request_payload.get("questions", []):
            items.append(
                {
                    "id": item["id"],
                    "knowledgePoints": ["力学/牛顿运动定律/受力分析"],
                    "tags": ["受力分析", "模型题"],
                    "category": "计算题",
                    "difficulty": 3,
                }
            )
        result = {"items": items}
    else:
        question = request_payload.get("question", {})
        result = {
            "question_id": question.get("question_id", ""),
            "analysis_structured": {
                "review": "先提取已知量与目标量。",
                "strategy": "根据模型选择对应的物理规律。",
                "steps": "分步列式并保持单位统一。",
                "conclusion": "整理得到最终结果。",
                "pitfalls": "注意方向、符号和单位。",
                "extension": "可继续讨论极端条件或变式设问。",
            },
            "analysis_text": "先审题，再建模，最后分步求解并回到物理意义。",
        }

    sys.stdout.write(json.dumps(_response(task_id, result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
