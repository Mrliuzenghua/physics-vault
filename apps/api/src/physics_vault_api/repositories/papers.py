from __future__ import annotations

from contextlib import closing

from ..database import connect_db
from ..paths import default_db_path
from ..schemas.papers import PaperDetail, PaperQuestionSummary, PaperSummary


class PaperRepository:
    """Read-only paper queries over the canonical question bank."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path

    def list(
        self,
        *,
        year: int | None,
        region: str | None,
        exam_type: str | None,
        query: str | None,
        subject: str,
        limit: int,
        offset: int,
    ) -> list[PaperSummary]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT p.paper_id, p.year, p.exam_type, p.region, p.paper_name,
                       p.subject, p.status, COUNT(qn.question_id) AS question_count
                FROM papers p
                LEFT JOIN questions qn ON qn.primary_paper_id = p.paper_id
                WHERE (? IS NULL OR p.year = ?)
                  AND (? IS NULL OR p.region = ?)
                  AND (? IS NULL OR p.exam_type = ?)
                  AND (? IS NULL OR p.subject = ?)
                  AND (? IS NULL OR p.paper_name LIKE '%' || ? || '%' OR p.paper_id LIKE '%' || ? || '%')
                GROUP BY p.paper_id
                ORDER BY p.year DESC, p.paper_id
                LIMIT ? OFFSET ?
                """,
                (year, year, region, region, exam_type, exam_type, subject, subject, query, query, query, limit, offset),
            ).fetchall()
        return [PaperSummary.model_validate(dict(row)) for row in rows]

    def get(self, paper_id: str) -> PaperDetail | None:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            row = connection.execute(
                """
                SELECT p.paper_id, p.year, p.exam_type, p.region, p.paper_name, p.subject,
                       p.status, p.source_path, p.source_format, p.notes, p.created_at, p.updated_at,
                       COUNT(q.question_id) AS question_count
                FROM papers p
                LEFT JOIN questions q ON q.primary_paper_id = p.paper_id
                WHERE p.paper_id = ?
                GROUP BY p.paper_id
                """,
                (paper_id,),
            ).fetchone()
        return PaperDetail.model_validate(dict(row)) if row else None

    def list_questions(self, paper_id: str) -> list[PaperQuestionSummary]:
        db_path = self._db_path or str(default_db_path())
        with closing(connect_db(db_path, writable=False)) as connection:
            rows = connection.execute(
                """
                SELECT question_id, canonical_title, module, topic2, topic3, difficulty,
                       question_type AS type, status, has_media, primary_paper_id,
                       primary_question_no, vault_markdown_path
                FROM questions WHERE primary_paper_id = ?
                ORDER BY primary_question_no, question_id
                """,
                (paper_id,),
            ).fetchall()
            question_ids = [str(row["question_id"]) for row in rows]
            knowledge_map: dict[str, list[dict]] = {}
            if question_ids:
                placeholders = ",".join("?" for _ in question_ids)
                links = connection.execute(
                    f"""
                    SELECT question_id, rank, topic1_id, topic1_name, topic2_id, topic2_name,
                           topic3_id, topic3_name, source_chapter, source, confidence, note
                    FROM question_knowledge_points_view
                    WHERE question_id IN ({placeholders})
                    ORDER BY question_id, rank
                    """,
                    question_ids,
                ).fetchall()
                for link in links:
                    payload = dict(link)
                    question_id = str(payload.pop("question_id"))
                    knowledge_map.setdefault(question_id, []).append(payload)
        items: list[PaperQuestionSummary] = []
        for row in rows:
            payload = dict(row)
            payload["difficulty"] = str(payload["difficulty"]) if payload["difficulty"] is not None else None
            payload["knowledge_points"] = knowledge_map.get(str(row["question_id"]), [])
            items.append(PaperQuestionSummary.model_validate(payload))
        return items
