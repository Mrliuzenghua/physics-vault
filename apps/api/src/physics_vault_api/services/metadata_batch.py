"""Batch metadata completion service.

Supports three modes:
- manual  — apply explicit values to all selected questions
- ai      — call the MCP metadata generator for auto-fill
- mixed   — manual values + AI for unset fields
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..bootstrap import configure_workspace_imports

configure_workspace_imports()

from mcp_contracts.src.models import (  # type: ignore[import-not-found]
    MetadataConstraints,
    MetadataTaskItem,
)

from ..repositories.question_write import QuestionWriteRepository
from ..schemas.metadata_batch import (
    BatchMetadataItemResult,
    BatchMetadataRequest,
    BatchMetadataResponse,
)
from .mcp_gateway import AppError, McpGatewayService

logger = logging.getLogger(__name__)


class MetadataBatchService:
    """Orchestrates batch metadata writes across AI and manual paths."""

    def __init__(
        self,
        repo: QuestionWriteRepository,
        gateway: McpGatewayService | None = None,
    ) -> None:
        self._repo = repo
        self._gateway = gateway
        self._repo.ensure_metadata_columns()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process(self, request: BatchMetadataRequest) -> BatchMetadataResponse:
        qids = request.question_ids
        results: list[BatchMetadataItemResult] = []
        updated = 0
        skipped = 0
        failed = 0

        # Fetch current metadata
        current = self._repo.get_question_metadata(qids)

        # Determine AI fields
        ai_fields = self._ai_fields(request)
        manual_values = request.manual_values or None

        # ── AI pass ──
        ai_results: dict[str, dict[str, Any]] = {}
        if ai_fields and self._gateway is not None:
            try:
                ai_results = await self._run_ai(qids, current, ai_fields, request)
            except AppError as exc:
                logger.warning("AI metadata generation failed: %s", exc.message)
                # AI failure → all AI-field questions are skipped with a note
                for qid in qids:
                    if any(self._field_is_empty(current.get(qid, {}), f) for f in ai_fields):
                        results.append(BatchMetadataItemResult(
                            question_id=qid, status="skipped",
                            message=f"AI 不可用: {exc.message}",
                        ))
                        skipped += 1
                remaining = [qid for qid in qids if qid not in {r.question_id for r in results}]
            else:
                remaining = qids
        else:
            remaining = qids
            ai_results = {}

        # ── Per-question update ──
        for qid in remaining:
            cur = current.get(qid, {})
            is_empty = {f: self._field_is_empty(cur, f) for f in request.fields}
            updates: dict[str, str | None] = {}
            updated_fields: list[str] = []

            for field in request.fields:
                if field == "knowledge_points":
                    updated_fields = self._resolve_kp(
                        qid, cur, is_empty, field, request, manual_values, ai_results, updates, updated_fields
                    )
                elif field == "tags":
                    updated_fields = self._resolve_tags(
                        qid, cur, is_empty, field, request, manual_values, ai_results, updates, updated_fields
                    )
                elif field == "source":
                    updated_fields = self._resolve_source(
                        qid, cur, is_empty, field, request, manual_values, ai_results, updates, updated_fields
                    )

            if not updates:
                results.append(BatchMetadataItemResult(
                    question_id=qid, status="skipped",
                    message="已有内容，已跳过" if not request.force_overwrite else "无需更新",
                ))
                skipped += 1
                continue

            try:
                self._repo.update_question_metadata(qid, updates)
                results.append(BatchMetadataItemResult(
                    question_id=qid, status="updated",
                    updated_fields=updated_fields,
                ))
                updated += 1
            except Exception as exc:
                logger.exception("Failed to update metadata for %s", qid)
                results.append(BatchMetadataItemResult(
                    question_id=qid, status="failed",
                    message=str(exc),
                ))
                failed += 1

        return BatchMetadataResponse(
            total=len(qids),
            updated=updated,
            skipped=skipped,
            failed=failed,
            results=results,
        )

    # ------------------------------------------------------------------
    # Field resolution helpers
    # ------------------------------------------------------------------

    def _resolve_kp(self, qid, cur, is_empty, field, request, manual_values, ai_results, updates, updated_fields):
        if not request.force_overwrite and not is_empty["knowledge_points"]:
            return updated_fields  # skip — has value
        manual_val = manual_values.knowledge_points if manual_values else None
        if manual_val:
            updates["knowledge_point"] = manual_val
        elif qid in ai_results and ai_results[qid].get("knowledge_points"):
            updates["knowledge_point"] = str(ai_results[qid]["knowledge_points"])
        if "knowledge_point" in updates:
            updated_fields.append(field)
        return updated_fields

    def _resolve_tags(self, qid, cur, is_empty, field, request, manual_values, ai_results, updates, updated_fields):
        if not request.force_overwrite and not is_empty["tags"]:
            return updated_fields
        manual_tags = manual_values.tags if manual_values else []
        ai_tags = ai_results.get(qid, {}).get("tags", [])
        new_tags = manual_tags if manual_tags else (ai_tags if isinstance(ai_tags, list) else [])

        if request.force_overwrite:
            merged = new_tags
        else:
            existing_tags = self._parse_tags(cur.get("tags_json"))
            all_tags = existing_tags + new_tags
            merged = list(dict.fromkeys(all_tags))  # dedup preserving order

        if merged:
            updates["tags_json"] = json.dumps(merged, ensure_ascii=False)
            updated_fields.append(field)
        return updated_fields

    def _resolve_source(self, qid, cur, is_empty, field, request, manual_values, ai_results, updates, updated_fields):
        if not request.force_overwrite and not is_empty["source"]:
            return updated_fields
        manual_val = manual_values.source if manual_values else None
        if manual_val:
            updates["source_text"] = manual_val
        elif qid in ai_results and ai_results[qid].get("source"):
            updates["source_text"] = str(ai_results[qid]["source"])
        if "source_text" in updates:
            updated_fields.append(field)
        return updated_fields

    # ------------------------------------------------------------------
    # AI call
    # ------------------------------------------------------------------

    def _ai_fields(self, request: BatchMetadataRequest) -> list[str]:
        """Fields that should be handled by AI."""
        if request.mode == "manual":
            return []
        if request.mode == "ai":
            return list(request.fields)
        # mixed mode: AI for fields not covered by manual_values
        mv = request.manual_values
        manual_covered: set[str] = set()
        if mv:
            if mv.knowledge_points:
                manual_covered.add("knowledge_points")
            if mv.tags:
                manual_covered.add("tags")
            if mv.source:
                manual_covered.add("source")
        return [f for f in request.fields if f not in manual_covered]

    async def _run_ai(
        self,
        qids: list[str],
        current: dict,
        fields: list[str],
        request: BatchMetadataRequest,
    ) -> dict[str, dict[str, Any]]:
        """Call MCP metadata generator and return {question_id: {field: value}}."""
        if self._gateway is None:
            return {}

        items = [
            MetadataTaskItem(
                id=qid,
                question=qid,
                knowledgePoints=[current.get(qid, {}).get("knowledge_point") or ""],
            )
            for qid in qids
        ]
        mcp_fields = self._map_fields_to_mcp(fields)

        raw = await self._gateway.generate_metadata({
            "items": [item.__dict__ for item in items],
            "fields": mcp_fields,
            "constraints": {},
            "only_fill_empty": not request.force_overwrite,
            "strict_enum_match": False,
        })

        out: dict[str, dict[str, Any]] = {}
        for item in raw.get("items", []):
            qid = item.get("id", "")
            entry: dict[str, Any] = {}
            kp_list = item.get("knowledgePoints")
            if kp_list and isinstance(kp_list, list) and kp_list:
                entry["knowledge_points"] = kp_list[0] if isinstance(kp_list[0], str) else str(kp_list[0])
            tags = item.get("tags")
            if isinstance(tags, list):
                entry["tags"] = tags
            src = item.get("source")
            if src and isinstance(src, str):
                entry["source"] = src
            out[qid] = entry
        return out

    @staticmethod
    def _map_fields_to_mcp(fields: list[str]) -> list[str]:
        m = {
            "knowledge_points": "knowledgePoints",
            "tags": "tags",
            "source": "source",
        }
        return [m[f] for f in fields if f in m]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _field_is_empty(cur: dict, field: str) -> bool:
        if field == "knowledge_points":
            return not cur.get("knowledge_point")
        if field == "tags":
            raw = cur.get("tags_json")
            return not raw or raw == "[]"
        if field == "source":
            return not cur.get("source_text")
        return True

    @staticmethod
    def _parse_tags(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
