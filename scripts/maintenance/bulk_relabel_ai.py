"""High-throughput, audited metadata relabelling for canonical questions.

The command is deliberately dry-run by default.  It sends only question
metadata supplied by the teacher's configured AI endpoint, validates the
response against the active topic tree, and writes only high-confidence
records through ``MetadataManagementService``.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
API_SRC = WORKSPACE / "apps" / "api" / "src"
os.environ.setdefault("PYTHONPATH", str(API_SRC))
import sys

if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from physics_vault_api.services.ai_http_client import AiHttpClient
from physics_vault_api.services.metadata_management import MetadataManagementService
from physics_vault_api.runtime_config import get_runtime_config


def load_dotenv(path: Path) -> None:
    """Load local settings without printing secrets or overwriting the shell."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def db_path() -> Path:
    configured = os.getenv("PHYSICS_DB_PATH", "").strip()
    if not configured:
        return WORKSPACE / "data" / "app-db" / "physics_vault.sqlite3"
    candidate = Path(configured)
    return candidate if candidate.is_absolute() else WORKSPACE / "apps" / "api" / candidate


def parse_json_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def load_batch(path: Path, after_id: str, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        topic_rows = conn.execute(
            """
            SELECT topic3_id, topic3_name, topic2_name, topic1_name
            FROM knowledge_points
            WHERE status = 'active'
            ORDER BY topic1_id, topic2_id, topic3_id
            """
        ).fetchall()
        rows = conn.execute(
            """
            SELECT q.question_id, q.question_type, q.difficulty, q.canonical_title,
                   qti.title_text, qti.stem_text, qti.analysis_text, qti.tags_json,
                   GROUP_CONCAT(qkp.topic3_id, '|') AS current_topic3_ids
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN question_knowledge_points qkp ON qkp.question_id = q.question_id
            WHERE q.question_id > ?
            GROUP BY q.question_id
            ORDER BY q.question_id
            LIMIT ?
            """,
            (after_id, limit),
        ).fetchall()

    questions = []
    for row in rows:
        title = str(row["title_text"] or row["canonical_title"] or "").strip()
        stem = str(row["stem_text"] or "").strip()
        analysis = str(row["analysis_text"] or "").strip()
        questions.append(
            {
                "question_id": row["question_id"],
                "question_type": row["question_type"],
                "title": title[:900],
                "stem": stem[:1800],
                "analysis": analysis[:1800],
                "current_topic3_ids": [item for item in str(row["current_topic3_ids"] or "").split("|") if item],
                "current_difficulty": row["difficulty"],
                "current_tags": parse_json_list(row["tags_json"]),
            }
        )
    topics = [dict(row) for row in topic_rows]
    return questions, topics


def classify(client: AiHttpClient, questions: list[dict[str, Any]], topics: list[dict[str, str]]) -> dict[str, Any]:
    topic_catalog = [
        {"id": item["topic3_id"], "name": item["topic3_name"], "parent": f"{item['topic1_name']}/{item['topic2_name']}"}
        for item in topics
    ]
    system = """你是高中物理题库元数据质检员。独立判定题目，不要被旧标签锚定。
只能使用给定的三级知识点 ID；每题 1 个主知识点，最多 2 个次级知识点。主知识点必须是解题第一步和决定性模型，不能仅按出现的词汇判断。
难度：1基础概念或直接代入；2常规两三步；3多概念/需建模；4综合推理链长；5竞赛或拔尖。
标签只写题型、方法或情境，不要重复知识点名称、上级目录或“难度X”。
只有单一、连贯的物理模型才可标为高置信。跨模块综合题、并列知识辨析题、实验信息不全题必须 review_required=true，且不要猜测。
若题干/解析不全、目录不精确或不能达到 0.90 置信度，confidence 填低于 0.90，review_required=true。
evidence 必须是题干或解析中逐字出现的、能支持主模型的 4–30 字原文片段。
返回严格 JSON：{"items":[{"question_id":"...","topic3_ids":["主ID","次ID"],"difficulty":1,"tags":["..."],"confidence":0.0,"review_required":false,"evidence":"原文片段","reason":"不超过40字"}]}。"""
    user = json.dumps({"topic_catalog": topic_catalog, "questions": questions}, ensure_ascii=False)
    return client._call(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        max_tokens=18000,
        response_format={"type": "json_object"},
        timeout_seconds=180,
        thinking="disabled",
    )


def validate(
    items: Any,
    topics: list[dict[str, str]],
    questions: list[dict[str, Any]],
    confidence_threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    accepted: list[dict[str, Any]] = []
    review: list[dict[str, str]] = []
    topic1_by_id = {item["topic3_id"]: item["topic1_name"] for item in topics}
    question_text_by_id = {
        item["question_id"]: " ".join(str(item.get(field) or "") for field in ("title", "stem", "analysis"))
        for item in questions
    }
    if not isinstance(items, list):
        return accepted, [{"question_id": "*", "reason": "AI response has no items list"}]
    for raw in items:
        if not isinstance(raw, dict):
            continue
        question_id = str(raw.get("question_id") or "").strip()
        topic3_ids = list(dict.fromkeys(str(item).strip() for item in raw.get("topic3_ids", []) if str(item).strip()))
        tags = list(dict.fromkeys(str(item).strip() for item in raw.get("tags", []) if str(item).strip()))[:8]
        try:
            difficulty = int(raw.get("difficulty"))
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError):
            difficulty, confidence = 0, 0.0
        reason = " ".join(str(raw.get("reason") or "").split())[:500]
        evidence = " ".join(str(raw.get("evidence") or "").split())
        same_branch = len({topic1_by_id.get(topic_id) for topic_id in topic3_ids}) == 1
        evidence_is_verbatim = 4 <= len(evidence) <= 30 and evidence in question_text_by_id.get(question_id, "")
        valid = (
            bool(question_id)
            and 1 <= difficulty <= 5
            and 1 <= len(topic3_ids) <= 2
            and all(topic_id in topic1_by_id for topic_id in topic3_ids)
            and same_branch
            and evidence_is_verbatim
            and confidence >= confidence_threshold
            and not bool(raw.get("review_required"))
        )
        if not valid:
            review.append({"question_id": question_id or "*", "reason": reason or "low confidence, cross-branch, or missing evidence"})
            continue
        accepted.append(
            {
                "question_id": question_id,
                "topic3_ids": topic3_ids,
                "difficulty": difficulty,
                "tags": tags,
                "knowledge_source": "ai_bulk_relabel",
                "knowledge_confidences": [confidence] * len(topic3_ids),
                "knowledge_note": f"高速重标：{reason}" if reason else "高速重标：高置信 AI 判定。",
            }
        )
    return accepted, review


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-id", default="Q00000020")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--confidence", type=float, default=0.85)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit must be in 1..100")
    load_dotenv(WORKSPACE / "apps" / "api" / ".env")
    runtime_llm = get_runtime_config().llm
    base_url = os.getenv("PHYSICS_LLM_BASE_URL", "").strip() or str(runtime_llm.base_url or "").strip()
    api_key = os.getenv("PHYSICS_LLM_API_KEY", "").strip() or str(runtime_llm.api_key or "").strip()
    model = os.getenv("PHYSICS_LLM_MODEL", "").strip() or str(runtime_llm.model_name or "").strip()
    if not base_url or not api_key or not model:
        raise SystemExit("Configured LLM endpoint is unavailable.")
    path = db_path()
    questions, topics = load_batch(path, args.after_id, args.limit)
    if not questions:
        print(json.dumps({"ok": True, "message": "no remaining questions"}, ensure_ascii=False))
        return
    response = classify(AiHttpClient(base_url, api_key, model), questions, topics)
    accepted, review = validate(response.get("items"), topics, questions, args.confidence)
    result: dict[str, Any] = {
        "ok": True,
        "dry_run": not args.apply,
        "requested": len(questions),
        "accepted": len(accepted),
        "review_count": len(review),
        "next_after_id": questions[-1]["question_id"],
        "preview": accepted[:10],
        "review": review,
    }
    if args.apply and accepted:
        result["write"] = MetadataManagementService(path).batch_update_question_metadata(
            accepted,
            reason=f"高速全库重标：{questions[0]['question_id']}–{questions[-1]['question_id']}；仅写入 AI 置信度≥{args.confidence:.2f} 的结果。",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
