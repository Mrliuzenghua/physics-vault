from __future__ import annotations

import json
import uuid
from pathlib import Path

from mcp_contracts.src.operation_plan import OperationPlan, snapshot_version

from ..database import connect_db
from ..repositories.knowledge_points import KnowledgePointRepository
from ..repositories.operation_plans import OperationPlanRepository
from ..schemas.knowledge_points import KnowledgePointItem, QuestionKnowledgePointBatchItem, QuestionKnowledgePointLink, QuestionKnowledgePointUpsert
from .operation_plans import OperationPlanService, build_question_knowledge_point_replace_plan


class KnowledgePointService:
    def __init__(
        self,
        repository: KnowledgePointRepository,
        operation_plan_service: OperationPlanService | None = None,
    ) -> None:
        self._repository = repository
        self._operation_plan_service = operation_plan_service or OperationPlanService(
            OperationPlanRepository(repository.database_path)
        )

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
        self._validate_replacement_items(items)
        return self._repository.replace_for_question(question_id, items)

    def preview_replacement_for_question(
        self,
        question_id: str,
        items: list[QuestionKnowledgePointBatchItem],
        reason: str,
    ) -> dict:
        """Persist one immutable knowledge-point replacement preview."""
        self._validate_replacement_items(items)
        clean_reason = " ".join(reason.split())
        if not clean_reason:
            raise ValueError("reason is required")
        before = self._repository.validate_replacement_for_question(question_id, items)
        if before is None:
            raise LookupError("Question not found")
        before_payload = [link.model_dump(mode="json") for link in before]
        replacement_payload = [item.model_dump(mode="json") for item in items]
        changed = _replacement_changed(before_payload, replacement_payload)
        result = {
            "question_id": question_id,
            "before_links": before_payload,
            "replacement_items": replacement_payload,
            "changed": changed,
            "requires_confirmation": changed,
            "operation_plan": None,
        }
        if not changed:
            return result
        plan = build_question_knowledge_point_replace_plan(
            question_id=question_id,
            before_links=before_payload,
            replacement_items=replacement_payload,
            reason=clean_reason,
        )
        self._operation_plan_service.save_preview(plan)
        result["operation_plan"] = plan
        return result

    def current_operation_version(self, plan: OperationPlan) -> str:
        """Rebuild the single target's immutable optimistic-lock token."""
        config = plan.version_snapshot.get("knowledge_point_replacement")
        question_id = plan.version_snapshot.get("question_id")
        if plan.action != "questions.knowledge_points.replace" or not isinstance(config, dict) or not isinstance(question_id, str):
            raise ValueError("unsupported knowledge-point operation plan")
        current = self._repository.list_for_question(question_id)
        if current is None:
            raise ValueError("Question not found")
        return snapshot_version(
            {
                "question_id": question_id,
                "before_links": [link.model_dump(mode="json") for link in current],
                "knowledge_point_replacement": config,
            }
        )

    def confirm_replacement_operation(self, operation_id: str):
        return self._operation_plan_service.execute(
            operation_id,
            version_reader=self.current_operation_version,
            executor=self.execute_replacement_operation,
        )

    def execute_replacement_operation(self, plan: OperationPlan) -> dict:
        """Execute only the stored replacement and append an audit snapshot."""
        config = plan.version_snapshot.get("knowledge_point_replacement")
        if plan.action != "questions.knowledge_points.replace" or not isinstance(config, dict):
            raise ValueError("unsupported knowledge-point operation plan")
        question_id = str(config.get("question_id") or "")
        raw_items = config.get("items")
        if not question_id or not isinstance(raw_items, list):
            raise ValueError("invalid knowledge-point operation payload")
        items = [QuestionKnowledgePointBatchItem.model_validate(item) for item in raw_items]
        self._validate_replacement_items(items)
        links = self._repository.replace_for_question(question_id, items)
        if links is None:
            raise ValueError("Question not found")
        after_payload = [link.model_dump(mode="json") for link in links]
        audit_batch_id = _record_knowledge_point_replacement_audit(
            self._repository.database_path,
            question_id=question_id,
            before_links=plan.version_snapshot.get("before_links", []),
            after_links=after_payload,
            reason=str(config.get("reason") or ""),
        )
        return {"question_id": question_id, "links": after_payload, "audit_batch_id": audit_batch_id}

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

    @staticmethod
    def _validate_replacement_items(items: list[QuestionKnowledgePointBatchItem]) -> None:
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


def _replacement_changed(before_links: list[dict], replacement_items: list[dict]) -> bool:
    """Ignore denormalized names and compare only persisted link columns."""
    def normalized(item: dict) -> dict:
        return {
            "rank": item["rank"], "topic3_id": item["topic3_id"],
            "source": item.get("source") or "manual",
            "confidence": float(item.get("confidence") if item.get("confidence") is not None else 1.0),
            "note": item.get("note"),
        }
    return sorted(map(normalized, before_links), key=lambda item: item["rank"]) != sorted(
        map(normalized, replacement_items), key=lambda item: item["rank"]
    )


def _record_knowledge_point_replacement_audit(
    db_path: str | None,
    *,
    question_id: str,
    before_links: object,
    after_links: list[dict],
    reason: str,
) -> str:
    """Record reversible before/after link sets in the canonical audit ledger."""
    batch_id = f"CHG-{uuid.uuid4().hex[:12]}"
    with connect_db(Path(db_path) if db_path else None, writable=True) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS change_batches (
            batch_id TEXT PRIMARY KEY, change_type TEXT NOT NULL, reason TEXT,
            source TEXT NOT NULL DEFAULT 'physics_vault_mcp', status TEXT NOT NULL DEFAULT 'applied',
            target_count INTEGER NOT NULL DEFAULT 0, changed_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, applied_at TEXT,
            rolled_back_at TEXT, rollback_reason TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS change_items (
            item_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL, field_name TEXT NOT NULL, before_value_json TEXT,
            after_value_json TEXT, status TEXT NOT NULL DEFAULT 'changed',
            risk_level TEXT NOT NULL DEFAULT 'medium', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(batch_id) REFERENCES change_batches(batch_id))""")
        conn.execute("""INSERT INTO change_batches (
            batch_id, change_type, reason, source, status, target_count, changed_count, applied_at
        ) VALUES (?, 'knowledge_point_replacement', ?, 'knowledge_point_operation', 'applied', 1, 1, CURRENT_TIMESTAMP)""",
            (batch_id, " ".join(reason.split())[:300] or None))
        conn.execute("""INSERT INTO change_items (
            item_id, batch_id, entity_type, entity_id, field_name,
            before_value_json, after_value_json, status, risk_level
        ) VALUES (?, ?, 'question', ?, 'question_knowledge_points', ?, ?, 'changed', 'medium')""",
            (f"CHI-{uuid.uuid4().hex[:12]}", batch_id, question_id,
             json.dumps(before_links, ensure_ascii=False), json.dumps(after_links, ensure_ascii=False)))
        conn.commit()
    return batch_id
