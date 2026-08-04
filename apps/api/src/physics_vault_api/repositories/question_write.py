"""Repository for batch-upserting questions into the SQLite database.

All SQLite access is confined to this module.  Business logic such as
validation, JSON serialisation and text assembly lives in the service layer.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path
from .review_queue import ReviewQueueRepository

logger = logging.getLogger(__name__)

# Reuse the same database path resolution as the rest of the API.
def _resolve_db_path(path: str | None = None) -> Path:
    if path:
        return Path(path)
    return default_db_path()


class QuestionWriteRepository:
    """Write-side data access for questions.

    Opens a connection per operation (no global pool) and runs every
    batch inside a single transaction so that the whole batch either
    commits or rolls back together.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {self._db_path}")
        conn = connect_db(self._db_path)
        self._ensure_version_table(conn)
        return conn

    @staticmethod
    def _ensure_version_table(conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS question_versions (
                version_id   TEXT PRIMARY KEY,
                question_id  TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                change_summary TEXT,
                modified_by  TEXT DEFAULT 'system',
                source       TEXT DEFAULT 'manual',
                created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_qv_question_id
            ON question_versions(question_id)
        """)

    # ------------------------------------------------------------------
    # Batch upsert
    # ------------------------------------------------------------------

    def upsert_many(
        self,
        questions: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Batch-upsert questions using ``question_id`` as the unique key.

        Each dict must contain the pre-serialised columns described below.
        The caller (service layer) is responsible for JSON encoding
        ``options`` / ``sub_questions`` / ``figures`` / ``tags`` and for
        building ``stem_text`` / ``canonical_title``.

        Returns ``{"received": N, "saved": N, "inserted": N, "updated": N}``.
        """
        received = len(questions)
        if received == 0:
            return {"received": 0, "saved": 0, "inserted": 0, "updated": 0}

        inserted = 0
        updated = 0

        with closing(self._get_connection()) as conn:
            try:
                for q in questions:
                    qid = q["question_id"]
                    _ensure_import_batch(conn, q.get("import_batch_id"), q.get("source_text"))

                    # — questions table —
                    row = conn.execute(
                        "SELECT question_id FROM questions WHERE question_id = ?", (qid,)
                    ).fetchone()

                    if row is None:
                        # New question — no prior version to capture
                        conn.execute(
                            """
                            INSERT INTO questions (
                                question_id, canonical_title, vault_markdown_path,
                                module, topic2, topic3, difficulty, question_type,
                                status, has_media, primary_paper_id, primary_question_no,
                                import_batch_id, origin_page, source,
                                content_hash, schema_version,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                      CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """,
                            (
                                qid,
                                q["canonical_title"],
                                q.get("vault_markdown_path") or f"import/{qid}.md",
                                q.get("knowledge_point") or None,
                                None,
                                None,
                                q.get("difficulty"),
                                q["question_type"],
                                q.get("status") or "已审核",
                                1 if (q.get("image_count") or 0) > 0 else 0,
                                q.get("primary_paper_id"),
                                q.get("primary_question_no"),
                                q.get("import_batch_id"),
                                q.get("source_page"),
                                q.get("source") or q.get("source_text"),
                                q.get("content_hash"),
                                q.get("schema_version") or "v2",
                            ),
                        )
                        inserted += 1
                    else:
                        # Capture version snapshot BEFORE update
                        _capture_version_snapshot(conn, qid, q)

                        conn.execute(
                            """
                            UPDATE questions SET
                                canonical_title = ?,
                                vault_markdown_path = ?,
                                module = ?,
                                topic2 = ?,
                                topic3 = ?,
                                difficulty = ?,
                                question_type = ?,
                                status = ?,
                                has_media = ?,
                                primary_paper_id = ?,
                                primary_question_no = ?,
                                import_batch_id = ?,
                                origin_page = ?,
                                source = ?,
                                content_hash = ?,
                                schema_version = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE question_id = ?
                            """,
                            (
                                q["canonical_title"],
                                q.get("vault_markdown_path") or f"import/{qid}.md",
                                q.get("knowledge_point") or None,
                                None,
                                None,
                                q.get("difficulty"),
                                q["question_type"],
                                q.get("status") or "已审核",
                                1 if (q.get("image_count") or 0) > 0 else 0,
                                q.get("primary_paper_id"),
                                q.get("primary_question_no"),
                                q.get("import_batch_id"),
                                q.get("source_page"),
                                q.get("source") or q.get("source_text"),
                                q.get("content_hash"),
                                q.get("schema_version") or "v2",
                                qid,
                            ),
                        )
                        updated += 1

                    # — question_text_index table —
                    tx_row = conn.execute(
                        "SELECT question_id FROM question_text_index WHERE question_id = ?",
                        (qid,),
                    ).fetchone()

                    if tx_row is None:
                        conn.execute(
                            """
                            INSERT INTO question_text_index (
                                question_id, paper_id, source_id, question_no,
                                markdown_path, title_text, stem_text, stem_clean_text,
                                answer_text, analysis_text,
                                options_json, sub_questions_json,
                                figures_json, image_asset_ids_json, image_filenames_json,
                                image_count, tags_json, source_text,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                      CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """,
                            (
                                qid,
                                q.get("primary_paper_id"),
                                q.get("source_region_id") or q.get("source_id"),
                                q.get("primary_question_no"),
                                q.get("vault_markdown_path") or f"import/{qid}.md",
                                q.get("title_text") or "",
                                q.get("stem_text") or "",
                                q.get("stem_clean_text"),
                                q.get("answer_text") or None,
                                q.get("analysis_text") or None,
                                q.get("options_json"),
                                q.get("sub_questions_json"),
                                q.get("figures_json"),
                                q.get("image_asset_ids_json"),
                                q.get("image_filenames_json"),
                                q.get("image_count") or 0,
                                q.get("tags_json"),
                                q.get("source_text"),
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE question_text_index SET
                                paper_id = ?,
                                source_id = ?,
                                question_no = ?,
                                markdown_path = ?,
                                title_text = ?,
                                stem_text = ?,
                                stem_clean_text = ?,
                                answer_text = ?,
                                analysis_text = ?,
                                options_json = ?,
                                sub_questions_json = ?,
                                figures_json = ?,
                                image_asset_ids_json = ?,
                                image_filenames_json = ?,
                                image_count = ?,
                                tags_json = ?,
                                source_text = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE question_id = ?
                            """,
                            (
                                q.get("primary_paper_id"),
                                q.get("source_region_id") or q.get("source_id"),
                                q.get("primary_question_no"),
                                q.get("vault_markdown_path") or f"import/{qid}.md",
                                q.get("title_text") or "",
                                q.get("stem_text") or "",
                                q.get("stem_clean_text"),
                                q.get("answer_text") or None,
                                q.get("analysis_text") or None,
                                q.get("options_json"),
                                q.get("sub_questions_json"),
                                q.get("figures_json"),
                                q.get("image_asset_ids_json"),
                                q.get("image_filenames_json"),
                                q.get("image_count") or 0,
                                q.get("tags_json"),
                                q.get("source_text"),
                                qid,
                            ),
                        )

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {
            "received": received,
            "saved": inserted + updated,
            "inserted": inserted,
            "updated": updated,
        }

    # ------------------------------------------------------------------
    # Batch delete
    # ------------------------------------------------------------------

    def delete_many(self, question_ids: list[str]) -> dict[str, Any]:
        """Delete questions by id.

        Child rows are removed by SQLite foreign-key cascades where the
        schema defines them. Image asset files are not deleted here; this
        only removes question records and their database bindings.
        """

        ordered_ids = list(dict.fromkeys(str(qid).strip() for qid in question_ids if str(qid).strip()))
        if not ordered_ids:
            return {"requested": 0, "deleted": 0, "missing_ids": []}

        placeholders = ",".join("?" for _ in ordered_ids)
        with closing(self._get_connection()) as conn:
            existing_rows = conn.execute(
                f"SELECT question_id FROM questions WHERE question_id IN ({placeholders})",
                ordered_ids,
            ).fetchall()
            existing = {row["question_id"] for row in existing_rows}
            missing = [qid for qid in ordered_ids if qid not in existing]

            if not existing:
                return {"requested": len(ordered_ids), "deleted": 0, "missing_ids": missing}

            existing_ids = [qid for qid in ordered_ids if qid in existing]
            delete_placeholders = ",".join("?" for _ in existing_ids)
            try:
                self._delete_question_bindings(conn, delete_placeholders, existing_ids)
                cursor = conn.execute(
                    f"DELETE FROM questions WHERE question_id IN ({delete_placeholders})",
                    existing_ids,
                )
                conn.execute(
                    f"DELETE FROM question_search_fts WHERE question_id IN ({delete_placeholders})",
                    existing_ids,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {
            "requested": len(ordered_ids),
            "deleted": cursor.rowcount if cursor.rowcount >= 0 else len(existing_ids),
            "missing_ids": missing,
        }

    def return_to_review(
        self,
        question_id: str,
        reason: str | None = None,
        reviewer: str | None = None,
    ) -> dict[str, Any]:
        """Move a live question back into the review queue for rework."""

        if not self._db_available():
            raise FileNotFoundError(f"Database file does not exist: {self._db_path}")

        review_id = f"REV-{uuid.uuid4().hex[:12]}"
        cleaned_reason = (reason or "题目需要回炉重造").strip() or "题目需要回炉重造"
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                "SELECT question_id FROM questions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row is None:
                return {
                    "question_id": question_id,
                    "review_id": None,
                    "status": "missing",
                }

            set_parts = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params: list[Any] = ["待校对"]
            if _table_has_column(conn, "questions", "review_status"):
                set_parts.insert(1, "review_status = ?")
                params.append("reviewing")
            if _table_has_column(conn, "questions", "review_comment"):
                set_parts.insert(-1, "review_comment = ?")
                params.append(cleaned_reason)
            params.append(question_id)
            conn.execute(
                f"UPDATE questions SET {', '.join(set_parts)} WHERE question_id = ?",
                params,
            )

            conn.commit()

        ReviewQueueRepository(migrate_legacy=False).enqueue_rework(
            review_id=review_id,
            question_id=question_id,
            reason=cleaned_reason,
            reviewer=reviewer,
        )

        return {
            "question_id": question_id,
            "review_id": review_id,
            "status": "queued",
        }

    @staticmethod
    def _delete_question_bindings(
        conn: sqlite3.Connection,
        placeholders: str,
        question_ids: list[str],
    ) -> None:
        """Remove rows that can keep deleted questions visible or blocked.

        Most current tables declare ON DELETE CASCADE / SET NULL, but some
        local databases have evolved through migrations. Explicit cleanup keeps
        deletion reliable across those older files too.
        """

        delete_tables = [
            "collection_questions",
            "favorite_items",
            "question_annotations",
            "question_assets",
            "question_knowledge_points",
            "question_sources",
            "question_text_index",
            "question_versions",
            "question_search_fts",
        ]
        null_tables = [
            "image_assets",
            "paper_draft_items",
            "processing_runs",
        ]

        for table in delete_tables:
            if _table_exists(conn, table):
                conn.execute(
                    f"DELETE FROM {table} WHERE question_id IN ({placeholders})",
                    question_ids,
                )

        for table in null_tables:
            if _table_exists(conn, table) and _table_has_column(conn, table, "question_id"):
                conn.execute(
                    f"UPDATE {table} SET question_id = NULL WHERE question_id IN ({placeholders})",
                    question_ids,
                )

        if _table_exists(conn, "review_queue"):
            conn.execute(
                f"""
                DELETE FROM review_queue
                WHERE entity_type = 'question' AND entity_id IN ({placeholders})
                """,
                question_ids,
            )

        if _table_exists(conn, "embeddings"):
            conn.execute(
                f"""
                DELETE FROM embeddings
                WHERE owner_type = 'question' AND owner_id IN ({placeholders})
                """,
                question_ids,
            )

    # ------------------------------------------------------------------
    # Metadata partial update
    # ------------------------------------------------------------------

    def _db_available(self) -> bool:
        """Check whether the database file is accessible."""
        return self._db_path.exists()

    def ensure_metadata_columns(self) -> None:
        """Add metadata columns to question_text_index if missing (idempotent)."""
        if not self._db_available():
            return
        with closing(self._get_connection()) as conn:
            for col, col_type in [("tags_json", "TEXT"), ("source_text", "TEXT")]:
                try:
                    conn.execute(f"ALTER TABLE question_text_index ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()

    def get_question_metadata(
        self, question_ids: list[str]
    ) -> dict[str, dict[str, str | None]]:
        """Return {question_id: {knowledge_point, tags_json, source_text}} for a batch."""
        if not question_ids or not self._db_available():
            return {}
        placeholders = ",".join("?" for _ in question_ids)
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                f"""
                SELECT q.question_id, q.module AS knowledge_point,
                       qti.tags_json, qti.source_text
                FROM questions q
                LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
                WHERE q.question_id IN ({placeholders})
                """,
                question_ids,
            ).fetchall()
        return {
            row["question_id"]: {
                "knowledge_point": row["knowledge_point"],
                "tags_json": row["tags_json"],
                "source_text": row["source_text"],
            }
            for row in rows
        }

    def update_question_metadata(
        self, question_id: str, updates: dict[str, str | None]
    ) -> None:
        """Update metadata fields for a single question."""
        if not self._db_available():
            return
        with closing(self._get_connection()) as conn:
            if "knowledge_point" in updates:
                conn.execute(
                    "UPDATE questions SET module = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                    (updates["knowledge_point"], question_id),
                )
            tags_json = updates.get("tags_json")
            source_text = updates.get("source_text")
            if tags_json is not None or source_text is not None:
                # Ensure the text_index row exists
                exists = conn.execute(
                    "SELECT 1 FROM question_text_index WHERE question_id = ?",
                    (question_id,),
                ).fetchone()
                if exists:
                    set_parts = []
                    params: list[str | None] = []
                    if tags_json is not None:
                        set_parts.append("tags_json = ?")
                        params.append(tags_json)
                    if source_text is not None:
                        set_parts.append("source_text = ?")
                        params.append(source_text)
                    if set_parts:
                        params.append(question_id)
                        conn.execute(
                            f"UPDATE question_text_index SET {', '.join(set_parts)}, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                            params,
                        )
                else:
                    conn.execute(
                        """
                        INSERT INTO question_text_index (question_id, tags_json, source_text, created_at, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                        (question_id, tags_json, source_text),
                    )
            conn.commit()

    # ------------------------------------------------------------------
    # Lightweight single-field update
    # ------------------------------------------------------------------

    def update_analysis(self, question_id: str, analysis_text: str) -> None:
        """Update only the analysis_text for a single question."""
        if not self._db_available():
            return
        with closing(self._get_connection()) as conn:
            conn.execute(
                """
                UPDATE question_text_index
                SET analysis_text = ?, updated_at = CURRENT_TIMESTAMP
                WHERE question_id = ?
                """,
                (analysis_text, question_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Mistake (错题) marking
    # ------------------------------------------------------------------

    def ensure_mistake_column(self) -> None:
        """Add is_mistake column to questions table if missing (idempotent)."""
        if not self._db_available():
            return
        with closing(self._get_connection()) as conn:
            try:
                conn.execute(
                    "ALTER TABLE questions ADD COLUMN is_mistake INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
            conn.commit()

    def set_mistake_status(self, question_id: str, is_mistake: bool) -> bool:
        """Mark or unmark a single question as mistake. Returns True if updated."""
        if not self._db_available():
            return False
        val = 1 if is_mistake else 0
        with closing(self._get_connection()) as conn:
            cur = conn.execute(
                "UPDATE questions SET is_mistake = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                (val, question_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def batch_set_mistake_status(
        self, question_ids: list[str], is_mistake: bool
    ) -> dict[str, int]:
        """Batch mark/unmark questions as mistake. Returns {updated, skipped, failed}."""
        updated = 0
        skipped = 0
        failed = 0
        val = 1 if is_mistake else 0
        if not self._db_available():
            return {"updated": 0, "skipped": 0, "failed": len(question_ids)}
        with closing(self._get_connection()) as conn:
            for qid in question_ids:
                try:
                    cur = conn.execute(
                        "UPDATE questions SET is_mistake = ?, updated_at = CURRENT_TIMESTAMP WHERE question_id = ?",
                        (val, qid),
                    )
                    if cur.rowcount > 0:
                        updated += 1
                    else:
                        skipped += 1
                except Exception:
                    failed += 1
            conn.commit()
        return {"updated": updated, "skipped": skipped, "failed": failed}

    def get_mistake_question_ids(self) -> list[str]:
        """Return all question_ids currently marked as mistakes."""
        if not self._db_available():
            return []
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                "SELECT question_id FROM questions WHERE is_mistake = 1 ORDER BY updated_at DESC"
            ).fetchall()
        return [row["question_id"] for row in rows]

    # ------------------------------------------------------------------
    # Question version history
    # ------------------------------------------------------------------

    def list_versions(self, question_id: str) -> list[dict[str, Any]]:
        """List all version records for a question (latest first)."""
        if not self._db_available():
            return []
        with closing(self._get_connection()) as conn:
            rows = conn.execute(
                """
                SELECT version_id, question_id, version_number,
                       change_summary, modified_by, source, created_at
                FROM question_versions
                WHERE question_id = ?
                ORDER BY version_number DESC
                """,
                (question_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        """Get a specific version's full snapshot."""
        if not self._db_available():
            return None
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                """
                SELECT version_id, question_id, version_number,
                       snapshot_json, change_summary, modified_by, source, created_at
                FROM question_versions
                WHERE version_id = ?
                """,
                (version_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        import json
        try:
            d["snapshot"] = json.loads(d.pop("snapshot_json"))
        except (json.JSONDecodeError, TypeError):
            d["snapshot"] = {}
        return d

    def get_latest_version_number(self, question_id: str) -> int:
        """Get the latest version number for a question (0 if none)."""
        if not self._db_available():
            return 0
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                "SELECT MAX(version_number) AS max_v FROM question_versions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
        return row["max_v"] or 0 if row else 0


# ── Module-level helper ──────────────────────────────────────────────

def _ensure_import_batch(
    conn: sqlite3.Connection,
    import_batch_id: str | None,
    source_text: str | None = None,
) -> None:
    """Ensure imported questions can keep their batch FK without requiring
    the separate persistent-batch flow to have inserted a row first.
    """
    batch_id = str(import_batch_id or "").strip()
    if not batch_id or batch_id == "IMPORT":
        return
    conn.execute(
        """
        INSERT INTO import_batches (
            import_batch_id, batch_name, source_type, source_path,
            pipeline_mode, status, total_files, total_questions, note
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)
        ON CONFLICT(import_batch_id) DO UPDATE SET
            source_path = COALESCE(import_batches.source_path, excluded.source_path),
            updated_at = datetime('now')
        """,
        (
            batch_id,
            batch_id,
            "review_import",
            source_text,
            "review_save",
            "confirmed",
            "Created by review save",
        ),
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def _capture_version_snapshot(
    conn: sqlite3.Connection,
    question_id: str,
    new_data: dict[str, Any],
    change_summary: str | None = None,
    modified_by: str = "system",
    source: str = "manual",
) -> None:
    """Capture the current question state as a version before an UPDATE."""
    import json

    # Read current state from questions + question_text_index
    q_row = conn.execute(
        """
        SELECT question_id, question_type, difficulty, module AS knowledge_point,
               status, primary_question_no, import_batch_id AS source
        FROM questions WHERE question_id = ?
        """,
        (question_id,),
    ).fetchone()

    tx_row = conn.execute(
        """
        SELECT stem_text, answer_text, analysis_text,
               options_json, sub_questions_json,
               image_asset_ids_json, image_filenames_json, image_count
        FROM question_text_index WHERE question_id = ?
        """,
        (question_id,),
    ).fetchone()

    if not q_row:
        return  # No existing question to snapshot

    snapshot = {
        "question_id": question_id,
        "question_type": q_row["question_type"],
        "title": (tx_row["stem_text"] or "").split("\n")[0] if tx_row else "",
        "stem_text": tx_row["stem_text"] if tx_row else "",
        "answer": tx_row["answer_text"] if tx_row else "",
        "analysis": tx_row["analysis_text"] if tx_row else "",
        "options_json": tx_row["options_json"] if tx_row else None,
        "sub_questions_json": tx_row["sub_questions_json"] if tx_row else None,
        "image_asset_ids_json": tx_row["image_asset_ids_json"] if tx_row else None,
        "image_filenames_json": tx_row["image_filenames_json"] if tx_row else None,
        "image_count": tx_row["image_count"] if tx_row else 0,
        "difficulty": q_row["difficulty"],
        "knowledge_point": q_row["knowledge_point"],
        "status": q_row["status"],
        "source": q_row["source"],
    }

    # Build a meaningful change summary
    if change_summary is None:
        changes: list[str] = []
        if new_data.get("stem_text") != snapshot.get("stem_text"):
            changes.append("题干变更")
        if new_data.get("answer_text") != snapshot.get("answer"):
            changes.append("答案变更")
        if new_data.get("analysis_text") != snapshot.get("analysis"):
            changes.append("解析变更")
        if new_data.get("difficulty") != snapshot.get("difficulty"):
            changes.append("难度调整")
        change_summary = "、".join(changes) if changes else "内容更新"

    # Determine next version number
    max_v = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) AS mv FROM question_versions WHERE question_id = ?",
        (question_id,),
    ).fetchone()
    next_version = (max_v["mv"] if max_v else 0) + 1

    import uuid
    version_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO question_versions (version_id, question_id, version_number,
            snapshot_json, change_summary, modified_by, source)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_id,
            question_id,
            next_version,
            json.dumps(snapshot, ensure_ascii=False),
            change_summary,
            modified_by,
            source,
        ),
    )
