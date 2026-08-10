from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import Any

from ..database import connect_db
from ..paths import default_db_path


APPROVED_STATUS = "\u5df2\u5ba1\u6838"


class QuestionImportRepository:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or str(default_db_path())

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        classification = payload["classification"]
        source = payload["source"]
        content = payload["content"]
        metadata = payload["metadata"]
        images = payload["images"]
        knowledge_points = payload["knowledge_points"]
        stem = str(content.get("stem") or "").strip()
        if not stem:
            raise ValueError("content.stem is required")
        question_type = str(classification.get("question_type") or "").strip()
        if not question_type:
            raise ValueError("classification.question_type is required")

        with closing(connect_db(self._db_path)) as connection:
            row = connection.execute(
                "SELECT MAX(CAST(SUBSTR(question_id, 2) AS INTEGER)) AS max_num FROM questions"
            ).fetchone()
            question_id = f"Q{int(row['max_num'] or 0) + 1:08d}"
            question_no = source.get("question_no")
            paper_id = source.get("paper_id") or None
            canonical_title = f"\u7b2c{question_no}\u9898" if question_no else "\u5bfc\u5165\u9898"
            markdown_path = metadata.get("vault_markdown_path") or f"import/{question_id}.md"
            text = _build_text(stem, content)
            try:
                connection.execute(
                    """
                    INSERT INTO questions (
                        question_id, canonical_title, vault_markdown_path, module, topic2, topic3,
                        difficulty, question_type, status, has_media, primary_paper_id,
                        primary_question_no, content_hash, schema_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'v2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        question_id, canonical_title, markdown_path,
                        classification.get("module"), classification.get("topic2"), classification.get("topic3"),
                        classification.get("difficulty"), question_type, APPROVED_STATUS, int(bool(images)),
                        paper_id, question_no,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO question_text_index (
                        question_id, paper_id, source_id, question_no, markdown_path, stem_text,
                        image_asset_ids_json, image_filenames_json, image_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        question_id, paper_id, metadata.get("source_id"), question_no, markdown_path, text,
                        json.dumps([item.get("asset_id") for item in images if item.get("asset_id")], ensure_ascii=False),
                        json.dumps([item.get("filename") for item in images if item.get("filename")], ensure_ascii=False),
                        len(images),
                    ),
                )
                inserted, skipped = self._link_knowledge_points(connection, question_id, knowledge_points)
                linked_images = self._link_images(connection, question_id, images)
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError(f"Import failed: {exc}") from exc
        return {
            "question_id": question_id,
            "status": APPROVED_STATUS,
            "knowledge_points_inserted": inserted,
            "images_linked": linked_images,
            "skipped_knowledge_points": skipped,
        }

    def delete(self, question_id: str) -> None:
        with closing(connect_db(self._db_path)) as connection:
            connection.execute("DELETE FROM questions WHERE question_id = ?", (question_id,))
            connection.commit()

    @staticmethod
    def _link_knowledge_points(connection, question_id: str, points: list[dict]) -> tuple[int, list[str]]:
        inserted = 0
        skipped: list[str] = []
        for point in points:
            topic3_id = str(point.get("topic3_id") or "").strip()
            if not topic3_id:
                continue
            exists = connection.execute(
                "SELECT 1 FROM knowledge_points WHERE topic3_id = ?", (topic3_id,)
            ).fetchone()
            if exists is None:
                skipped.append(topic3_id)
                continue
            rank = int(point.get("rank") or 1)
            connection.execute(
                """
                INSERT INTO question_knowledge_points (
                    link_id, question_id, rank, topic3_id, source, confidence, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id, rank) DO UPDATE SET
                    topic3_id=excluded.topic3_id, source=excluded.source,
                    confidence=excluded.confidence, note=excluded.note, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    f"{question_id}-KP-{rank}", question_id, rank, topic3_id,
                    point.get("source") or "manual", point.get("confidence", 1.0), point.get("note"),
                ),
            )
            inserted += 1
        return inserted, skipped

    @staticmethod
    def _link_images(connection, question_id: str, images: list[dict]) -> int:
        linked = 0
        for image in images:
            asset_id = str(image.get("asset_id") or "").strip()
            if not asset_id:
                continue
            exists = connection.execute(
                "SELECT 1 FROM image_assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            if exists is None:
                continue
            connection.execute(
                """
                INSERT INTO question_assets (
                    link_id, question_id, asset_id, placeholder_key, role, sort_order,
                    is_primary, is_verified, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id, asset_id) DO UPDATE SET
                    placeholder_key=excluded.placeholder_key, role=excluded.role,
                    sort_order=excluded.sort_order, is_primary=excluded.is_primary,
                    is_verified=excluded.is_verified, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    f"{question_id}-{asset_id}", question_id, asset_id, image.get("placeholder_key"),
                    image.get("role") or "stem", image.get("sort_order", 1),
                    int(image.get("is_primary", True)), int(image.get("verified", False)),
                ),
            )
            linked += 1
        return linked


def _build_text(stem: str, content: dict[str, Any]) -> str:
    parts = [stem]
    parts.extend(f"{item.get('label', '')}. {item.get('text', '')}" for item in content.get("options") or [])
    parts.extend(f"({item.get('index', '')}){item.get('stem', '')}" for item in content.get("sub_questions") or [])
    for field, label in (("answer", "\u3010\u7b54\u6848\u3011"), ("analysis", "\u3010\u89e3\u6790\u3011"), ("tips", "\u3010\u70b9\u775b\u3011")):
        if content.get(field):
            parts.append(f"{label}{content[field]}")
    return "\n".join(parts)
