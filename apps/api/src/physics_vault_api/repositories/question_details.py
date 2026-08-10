from __future__ import annotations

import json
from contextlib import closing

from ..database import connect_db
from ..paths import default_db_path
from ..schemas.question_details import QuestionAsset, QuestionDetail


def _decode_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _decode_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


class QuestionDetailRepository:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def get(self, question_id: str) -> QuestionDetail | None:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            row = connection.execute(
                """
                SELECT q.question_id, q.canonical_title, q.module, q.topic2, q.topic3,
                       q.difficulty, q.question_type AS type, q.status, q.has_media,
                       q.primary_paper_id, q.primary_question_no, q.vault_markdown_path,
                       q.content_hash, q.schema_version, q.created_at, q.updated_at,
                       qti.stem_text, qti.title_text, qti.stem_clean_text, qti.source_id,
                       COALESCE(qti.source_text, q.source, q.primary_paper_id) AS source,
                       qti.figures_json, qti.image_asset_ids_json, qti.image_filenames_json,
                       COALESCE(qti.image_count, 0) AS image_count, qti.answer_text,
                       qti.analysis_text, qti.tips_text, qti.options_json
                FROM questions q
                LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
                WHERE q.question_id = ?
                """,
                (question_id,),
            ).fetchone()
            if row is None:
                return None
            links = connection.execute(
                """
                SELECT rank, topic1_id, topic1_name, topic2_id, topic2_name, topic3_id,
                       topic3_name, source_chapter, source, confidence, note
                FROM question_knowledge_points_view
                WHERE question_id = ? ORDER BY rank
                """,
                (question_id,),
            ).fetchall()
        payload = dict(row)
        payload["difficulty"] = str(payload["difficulty"]) if payload["difficulty"] is not None else None
        payload["image_asset_ids"] = _decode_list(payload.pop("image_asset_ids_json", None))
        payload["image_filenames"] = _decode_list(payload.pop("image_filenames_json", None))
        payload["figures"] = _decode_json_list(payload.pop("figures_json", None))
        payload["knowledge_points"] = [dict(link) for link in links]
        return QuestionDetail.model_validate(payload)

    def get_write_payload(self, question_id: str) -> dict | None:
        """Return a complete writer-compatible baseline for a partial PUT update."""

        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            row = connection.execute(
                """
                SELECT q.question_id, q.question_type, q.difficulty, q.module AS knowledge_point,
                       q.import_batch_id, q.source, q.origin_page AS source_page,
                       qti.title_text, qti.stem_text, qti.stem_clean_text,
                       qti.options_json, qti.sub_questions_json, qti.figures_json,
                       qti.answer_text, qti.analysis_text, qti.tags_json, qti.source_text
                FROM questions q
                LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
                WHERE q.question_id = ?
                """,
                (question_id,),
            ).fetchone()
            if row is None:
                return None
            asset_rows = connection.execute(
                """
                SELECT qa.asset_id, qa.placeholder_key, ia.file_path
                FROM question_assets qa
                INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
                WHERE qa.question_id = ?
                """,
                (question_id,),
            ).fetchall()

        data = dict(row)
        paths_by_ref = {
            str(ref): str(file_path)
            for asset_id, placeholder_key, file_path in asset_rows
            for ref in (asset_id, placeholder_key)
            if ref and file_path
        }
        figures: list[dict] = []
        for item in _decode_json_list(data.get("figures_json")):
            if not isinstance(item, dict):
                continue
            figure = dict(item)
            ref = str(figure.get("fig_uuid") or figure.get("asset_id") or "")
            if paths_by_ref.get(ref):
                figure["local_path"] = paths_by_ref[ref]
            figures.append(figure)
        return {
            "question_id": question_id,
            "question_type": data.get("question_type") or "calculation",
            "title": data.get("title_text") or str(data.get("stem_text") or "").split("\n")[0],
            "options": _decode_json_list(data.get("options_json")),
            "answer": data.get("answer_text") or "",
            "analysis": data.get("analysis_text") or "",
            "sub_questions": _decode_json_list(data.get("sub_questions_json")),
            "figures": figures,
            "difficulty": data.get("difficulty"),
            "knowledge_point": data.get("knowledge_point") or "",
            "tags": _decode_json_list(data.get("tags_json")),
            "source": data.get("source") or "",
            "source_raw": data.get("source_text") or data.get("source") or "",
            "import_batch_id": data.get("import_batch_id"),
            "source_page": data.get("source_page"),
            "raw_text": data.get("stem_clean_text") or "",
        }

    def list_assets(self, question_id: str) -> list[QuestionAsset]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT qa.link_id, qa.asset_id, qa.role, qa.sort_order, qa.placeholder_key,
                       qa.is_primary, qa.is_verified, ia.filename, ia.file_path, ia.mime_type,
                       ia.width, ia.height, ia.description, ia.binding_confidence, ia.verified
                FROM question_assets qa
                INNER JOIN image_assets ia ON ia.asset_id = qa.asset_id
                WHERE qa.question_id = ?
                ORDER BY qa.sort_order, qa.asset_id
                """,
                (question_id,),
            ).fetchall()
        return [QuestionAsset.model_validate(dict(row)) for row in rows]
