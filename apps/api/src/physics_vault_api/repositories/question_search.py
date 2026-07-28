from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database path resolution (mirrors legacy_app.py logic)
# ---------------------------------------------------------------------------

_DB_PATH = default_db_path()


def _resolve_db_path(path: str | None = None) -> Path:
    if path:
        return Path(path)
    return _DB_PATH


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Mock data (used when SQLite database is unavailable)
# ---------------------------------------------------------------------------

_MOCK_QUESTIONS: list[dict[str, Any]] = [
    {
        "question_id": "Q00000001",
        "canonical_title": "匀加速直线运动基本公式",
        "module": "力学",
        "topic2": "运动学",
        "topic3": "匀变速直线运动",
        "difficulty": "2",
        "question_type": "single_choice",
        "status": "已审核",
        "has_media": False,
        "primary_paper_id": "PAPER-001",
        "primary_question_no": 1,
        "vault_markdown_path": "topics/mechanics/kinematics/Q00000001.md",
        "answer_text": "C",
        "analysis_text": "由 v = v₀ + at 可知…",
        "options_json": '[{"label":"A","text":"v = at"},{"label":"B","text":"v = v₀"},{"label":"C","text":"v = v₀ + at"},{"label":"D","text":"v² = v₀² + 2ax"}]',
        "image_count": 0,
        "paper_year": 2026,
        "paper_region": "全国",
        "paper_exam_type": "高考",
    },
    {
        "question_id": "Q00000002",
        "canonical_title": "牛顿第二定律应用",
        "module": "力学",
        "topic2": "牛顿定律",
        "topic3": "牛顿第二定律",
        "difficulty": "3",
        "question_type": "calculation",
        "status": "已审核",
        "has_media": True,
        "primary_paper_id": "PAPER-001",
        "primary_question_no": 2,
        "vault_markdown_path": "topics/mechanics/newton/Q00000002.md",
        "answer_text": "F = 10 N",
        "analysis_text": "根据 F = ma…",
        "options_json": None,
        "image_count": 1,
        "paper_year": 2026,
        "paper_region": "全国",
        "paper_exam_type": "高考",
    },
    {
        "question_id": "Q00000003",
        "canonical_title": "电场强度计算",
        "module": "电磁学",
        "topic2": "电场",
        "topic3": "电场强度",
        "difficulty": "4",
        "question_type": "multi_choice",
        "status": "待校验",
        "has_media": True,
        "primary_paper_id": "PAPER-002",
        "primary_question_no": 5,
        "vault_markdown_path": "topics/electromagnetism/electric_field/Q00000003.md",
        "answer_text": "AB",
        "analysis_text": "由 E = F/q 和 E = kQ/r²…",
        "options_json": '[{"label":"A","text":"E = F/q"},{"label":"B","text":"E = kQ/r²"},{"label":"C","text":"E = q/r"},{"label":"D","text":"E = F·q"}]',
        "image_count": 2,
        "paper_year": 2025,
        "paper_region": "北京",
        "paper_exam_type": "模拟",
    },
    {
        "question_id": "Q00000004",
        "canonical_title": "动量守恒定律",
        "module": "力学",
        "topic2": "动量",
        "topic3": "动量守恒",
        "difficulty": "3",
        "question_type": "calculation",
        "status": "已审核",
        "has_media": False,
        "primary_paper_id": "PAPER-003",
        "primary_question_no": 3,
        "vault_markdown_path": "topics/mechanics/momentum/Q00000004.md",
        "answer_text": "v₁ = 2 m/s",
        "analysis_text": "根据动量守恒 m₁v₁₀ + m₂v₂₀ = m₁v₁ + m₂v₂…",
        "options_json": None,
        "image_count": 0,
        "paper_year": 2024,
        "paper_region": "上海",
        "paper_exam_type": "高考",
    },
    {
        "question_id": "Q00000005",
        "canonical_title": "简谐运动周期",
        "module": "力学",
        "topic2": "振动与波",
        "topic3": "简谐运动",
        "difficulty": "5",
        "question_type": "single_choice",
        "status": "已确认",
        "has_media": False,
        "primary_paper_id": "PAPER-002",
        "primary_question_no": 10,
        "vault_markdown_path": "topics/mechanics/oscillation/Q00000005.md",
        "answer_text": "D",
        "analysis_text": "T = 2π√(m/k)…",
        "options_json": '[{"label":"A","text":"T = π√(m/k)"},{"label":"B","text":"T = π√(k/m)"},{"label":"C","text":"T = √(m/k)"},{"label":"D","text":"T = 2π√(m/k)"}]',
        "image_count": 0,
        "paper_year": 2024,
        "paper_region": "江苏",
        "paper_exam_type": "高考",
    },
]

_MOCK_KNOWLEDGE_POINTS: dict[str, list[dict[str, Any]]] = {
    "Q00000001": [
        {
            "rank": 1,
            "topic1_id": "T1-MEC",
            "topic1_name": "力学",
            "topic2_id": "T2-MEC-001",
            "topic2_name": "运动学",
            "topic3_id": "T3-MEC-001",
            "topic3_name": "匀变速直线运动",
            "source_chapter": "第一章",
            "source": "manual",
            "confidence": 1.0,
            "note": None,
        }
    ],
    "Q00000002": [
        {
            "rank": 1,
            "topic1_id": "T1-MEC",
            "topic1_name": "力学",
            "topic2_id": "T2-MEC-002",
            "topic2_name": "牛顿定律",
            "topic3_id": "T3-MEC-005",
            "topic3_name": "牛顿第二定律",
            "source_chapter": "第二章",
            "source": "manual",
            "confidence": 1.0,
            "note": None,
        }
    ],
    "Q00000003": [
        {
            "rank": 1,
            "topic1_id": "T1-ELC",
            "topic1_name": "电磁学",
            "topic2_id": "T2-ELC-001",
            "topic2_name": "电场",
            "topic3_id": "T3-ELC-001",
            "topic3_name": "电场强度",
            "source_chapter": "第六章",
            "source": "manual",
            "confidence": 1.0,
            "note": None,
        }
    ],
    "Q00000004": [
        {
            "rank": 1,
            "topic1_id": "T1-MEC",
            "topic1_name": "力学",
            "topic2_id": "T2-MEC-003",
            "topic2_name": "动量",
            "topic3_id": "T3-MEC-010",
            "topic3_name": "动量守恒",
            "source_chapter": "第三章",
            "source": "manual",
            "confidence": 1.0,
            "note": None,
        }
    ],
    "Q00000005": [
        {
            "rank": 1,
            "topic1_id": "T1-MEC",
            "topic1_name": "力学",
            "topic2_id": "T2-MEC-004",
            "topic2_name": "振动与波",
            "topic3_id": "T3-MEC-015",
            "topic3_name": "简谐运动",
            "source_chapter": "第四章",
            "source": "manual",
            "confidence": 1.0,
            "note": None,
        }
    ],
}


# ---------------------------------------------------------------------------
# Repository protocol / interface
# ---------------------------------------------------------------------------


class QuestionSearchRepository:
    """Data-access layer for question search.

    If *db_path* points to an existing SQLite file it is used directly;
    otherwise the repository falls back to a small in-memory mock dataset
    so the API surface remains testable without a physical database.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._mock = not self._has_searchable_questions()

        if self._mock:
            logger.warning(
                "QuestionSearchRepository: database not found at %s – using mock fallback.",
                self._db_path,
            )

    def _has_searchable_questions(self) -> bool:
        if not self._db_path.exists():
            return False
        try:
            with closing(connect_db(self._db_path, writable=False)) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'questions'
                    """
                ).fetchone()
                if not row or row["count"] == 0:
                    return False
                count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
                return count > 0
        except sqlite3.Error:
            return False

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Open a new SQLite connection (real or in-memory)."""
        if self._mock:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            logger.debug("QuestionSearchRepository: opened in-memory connection.")
            return conn

        return connect_db(self._db_path, writable=False)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_questions(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        search_mode: str = "browse",
        query: str | None = None,
        year: int | None = None,
        module: str | None = None,
        question_type: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        topic1_id: str | None = None,
        topic2_id: str | None = None,
        topic3_id: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        region: str | None = None,
        exam_type: str | None = None,
        has_media: bool | None = None,
        image_count_min: int = 0,
        is_mistake: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return ``(rows, total_count)`` for the given filter set.

        *rows* are flat dicts that the service layer maps into
        ``QuestionItem``; *total_count* is the un-paginated match count.
        """

        if self._mock:
            return self._mock_search(
                query=query,
                year=year,
                module=module,
                question_type=question_type,
                difficulty=difficulty,
                status=status,
                topic2=topic2,
                topic3=topic3,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                is_mistake=is_mistake,
                limit=limit,
                offset=offset,
            )

        return self._sqlite_search(
            search_mode=search_mode,
            query=query,
            year=year,
            module=module,
            question_type=question_type,
            difficulty=difficulty,
            status=status,
            topic1_id=topic1_id,
            topic2_id=topic2_id,
            topic3_id=topic3_id,
            topic2=topic2,
            topic3=topic3,
            region=region,
            exam_type=exam_type,
            has_media=has_media,
            image_count_min=image_count_min,
            is_mistake=is_mistake,
            limit=limit,
            offset=offset,
        )

    def _mock_search(
        self,
        query: str | None,
        year: int | None,
        module: str | None,
        question_type: str | None,
        difficulty: str | None,
        status: str | None,
        topic2: str | None,
        topic3: str | None,
        is_mistake: bool | None,
        topic1_id: str | None = None,
        topic2_id: str | None = None,
        topic3_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        filtered = list(_MOCK_QUESTIONS)

        if query:
            q = query.lower()
            filtered = [
                item
                for item in filtered
                if q in (item["canonical_title"] or "").lower()
                or q in (item.get("answer_text") or "").lower()
                or q in (item.get("analysis_text") or "").lower()
            ]

        if year is not None:
            filtered = [item for item in filtered if item.get("paper_year") == year]
        if module:
            filtered = [item for item in filtered if item.get("module") == module]
        if question_type:
            filtered = [item for item in filtered if item.get("question_type") == question_type]
        if difficulty:
            filtered = [item for item in filtered if item.get("difficulty") == difficulty]
        if status:
            filtered = [item for item in filtered if item.get("status") == status]
        if topic2:
            filtered = [item for item in filtered if item.get("topic2") == topic2]
        if topic3:
            filtered = [item for item in filtered if item.get("topic3") == topic3]
        # Filter by knowledge point IDs via the mock knowledge_points map
        if topic1_id or topic2_id or topic3_id:
            filtered = [
                item for item in filtered
                if any(
                    (not topic1_id or kp.get("topic1_id") == topic1_id)
                    and (not topic2_id or kp.get("topic2_id") == topic2_id)
                    and (not topic3_id or kp.get("topic3_id") == topic3_id)
                    for kp in _MOCK_KNOWLEDGE_POINTS.get(item["question_id"], [])
                )
            ]
        if is_mistake is not None:
            filtered = [item for item in filtered if bool(item.get("is_mistake", False)) == is_mistake]

        total = len(filtered)
        page = filtered[offset : offset + limit]
        return page, total

    def _sqlite_search(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        search_mode: str,
        query: str | None,
        year: int | None,
        module: str | None,
        question_type: str | None,
        difficulty: str | None,
        status: str | None,
        topic1_id: str | None,
        topic2_id: str | None,
        topic3_id: str | None,
        topic2: str | None,
        topic3: str | None,
        region: str | None,
        exam_type: str | None,
        has_media: bool | None,
        image_count_min: int,
        is_mistake: bool | None,
        limit: int,
        offset: int,
        _force_like: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        apply_keyword = search_mode == "strict" and bool(query)
        use_fts = apply_keyword and not _force_like and self._fts_available()

        base_sql = """
            SELECT DISTINCT
                q.question_id,
                q.canonical_title,
                q.module,
                q.topic2,
                q.topic3,
                q.difficulty,
                q.question_type,
                q.status,
                q.has_media,
                q.primary_paper_id,
                q.primary_question_no,
                q.vault_markdown_path,
                qti.stem_text,
                qti.answer_text,
                qti.analysis_text,
                qti.options_json,
                qti.image_asset_ids_json,
                qti.image_filenames_json,
                COALESCE(qti.image_count, 0) AS image_count,
                COALESCE(q.is_mistake, 0) AS is_mistake,
                q.mistake_marked_at,
                p.year AS paper_year,
                p.region AS paper_region,
                p.exam_type AS paper_exam_type
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN papers p ON p.paper_id = q.primary_paper_id
        """
        if use_fts:
            base_sql += """
            INNER JOIN question_search_fts
                ON question_search_fts.question_id = q.question_id
            """

        where: list[str] = []
        params: list[Any] = []

        def _add(value: Any, clause: str) -> None:
            if value is not None:
                where.append(clause)
                params.append(value)

        def _add_knowledge(condition: str, value: Any) -> None:
            if value is not None:
                where.append(
                    f"""
                    EXISTS (
                        SELECT 1
                        FROM question_knowledge_points_view kpv
                        WHERE kpv.question_id = q.question_id
                          AND {condition}
                    )
                    """
                )
                params.append(value)

        _add(year, "p.year = ?")
        _add(region, "p.region = ?")
        _add(exam_type, "p.exam_type = ?")
        _add(module, "q.module = ?")
        _add(topic2, "q.topic2 = ?")
        _add(topic3, "q.topic3 = ?")
        _add(question_type, "q.question_type = ?")
        _add(difficulty, "q.difficulty = ?")
        _add(status, "q.status = ?")
        _add(image_count_min if image_count_min > 0 else None, "COALESCE(qti.image_count, 0) >= ?")
        _add(1 if is_mistake is True else (0 if is_mistake is False else None), "COALESCE(q.is_mistake, 0) = ?")

        if has_media is not None:
            _add(1 if has_media else 0, "q.has_media = ?")

        _add_knowledge("kpv.topic1_id = ?", topic1_id)
        _add_knowledge("kpv.topic2_id = ?", topic2_id)
        _add_knowledge("kpv.topic3_id = ?", topic3_id)

        if use_fts and query:
            where.append("question_search_fts MATCH ?")
            params.append(_build_fts_query(query))
        elif apply_keyword and query:
            where.append(
                """(
                    q.canonical_title LIKE '%' || ? || '%'
                    OR qti.stem_text LIKE '%' || ? || '%'
                    OR qti.answer_text LIKE '%' || ? || '%'
                    OR qti.analysis_text LIKE '%' || ? || '%'
                )"""
            )
            params.extend([query, query, query, query])

        sql = base_sql
        if where:
            where_clause = " WHERE " + " AND ".join(where)
        else:
            where_clause = ""

        count_sql = """
            SELECT COUNT(DISTINCT q.question_id)
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN papers p ON p.paper_id = q.primary_paper_id
        """
        if use_fts:
            count_sql += """
            INNER JOIN question_search_fts
                ON question_search_fts.question_id = q.question_id
            """
        count_sql += where_clause

        sql += where_clause
        sql += " ORDER BY q.primary_question_no, q.question_id"
        sql += " LIMIT ? OFFSET ?"

        with closing(self._get_connection()) as conn:
            total = conn.execute(count_sql, params).fetchone()[0]

            rows = conn.execute(sql, params + [limit, offset]).fetchall()
            knowledge_map = self._fetch_knowledge_points(
                conn, [row["question_id"] for row in rows]
            )

        if use_fts and total == 0 and query:
            return self._sqlite_search(
                search_mode=search_mode,
                query=query,
                year=year,
                module=module,
                question_type=question_type,
                difficulty=difficulty,
                status=status,
                topic1_id=topic1_id,
                topic2_id=topic2_id,
                topic3_id=topic3_id,
                topic2=topic2,
                topic3=topic3,
                region=region,
                exam_type=exam_type,
                has_media=has_media,
                image_count_min=image_count_min,
                is_mistake=is_mistake,
                limit=limit,
                offset=offset,
                _force_like=True,
            )

        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _row_to_dict(row)
            payload["knowledge_points"] = knowledge_map.get(row["question_id"], [])
            result.append(payload)

        return result, total

    def get_questions_by_ids(self, question_ids: list[str]) -> list[dict[str, Any]]:
        ordered_ids = list(dict.fromkeys(qid for qid in question_ids if qid))
        if not ordered_ids:
            return []

        if self._mock:
            by_id = {item["question_id"]: item for item in _MOCK_QUESTIONS}
            return [by_id[qid] for qid in ordered_ids if qid in by_id]

        placeholders = ",".join("?" for _ in ordered_ids)
        order_case = "CASE q.question_id " + " ".join(
            f"WHEN ? THEN {index}" for index, _ in enumerate(ordered_ids)
        ) + " END"
        sql = f"""
            SELECT DISTINCT
                q.question_id,
                q.canonical_title,
                q.module,
                q.topic2,
                q.topic3,
                q.difficulty,
                q.question_type,
                q.status,
                q.has_media,
                q.primary_paper_id,
                q.primary_question_no,
                q.vault_markdown_path,
                qti.stem_text,
                qti.answer_text,
                qti.analysis_text,
                qti.options_json,
                qti.image_asset_ids_json,
                qti.image_filenames_json,
                COALESCE(qti.image_count, 0) AS image_count,
                COALESCE(q.is_mistake, 0) AS is_mistake,
                q.mistake_marked_at,
                p.year AS paper_year,
                p.region AS paper_region,
                p.exam_type AS paper_exam_type
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            LEFT JOIN papers p ON p.paper_id = q.primary_paper_id
            WHERE q.question_id IN ({placeholders})
            ORDER BY {order_case}
        """

        with closing(self._get_connection()) as conn:
            rows = conn.execute(sql, ordered_ids + ordered_ids).fetchall()
            knowledge_map = self._fetch_knowledge_points(
                conn, [row["question_id"] for row in rows]
            )

        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _row_to_dict(row)
            payload["knowledge_points"] = knowledge_map.get(row["question_id"], [])
            result.append(payload)
        return result

    def _fts_available(self) -> bool:
        with closing(self._get_connection()) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'question_search_fts'
                """
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Knowledge points batch fetch
    # ------------------------------------------------------------------

    def _fetch_knowledge_points(
        self,
        conn: sqlite3.Connection,
        question_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not question_ids:
            return {}
        placeholders = ",".join("?" for _ in question_ids)
        try:
            rows = conn.execute(
                f"""
                SELECT
                    question_id, rank,
                    topic1_id, topic1_name,
                    topic2_id, topic2_name,
                    topic3_id, topic3_name,
                    source_chapter, source, confidence, note
                FROM question_knowledge_points_view
                WHERE question_id IN ({placeholders})
                ORDER BY question_id, rank
                """,
                question_ids,
            ).fetchall()
        except sqlite3.OperationalError:
            # View may not exist; fall back to joining tables directly
            rows = []
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            d = _row_to_dict(row)
            qid = d.pop("question_id")
            grouped.setdefault(qid, []).append(d)
        return grouped

    # ------------------------------------------------------------------
    # Facets
    # ------------------------------------------------------------------

    def get_facets(self) -> dict[str, Any]:
        """Return distinct filter values across all tables."""
        if self._mock:
            return self._mock_facets()
        return self._sqlite_facets()

    def _mock_facets(self) -> dict[str, Any]:
        years_set = sorted({item["paper_year"] for item in _MOCK_QUESTIONS}, reverse=True)
        return {
            "years": years_set,
            "regions": sorted({item["paper_region"] for item in _MOCK_QUESTIONS}),
            "exam_types": sorted({item["paper_exam_type"] for item in _MOCK_QUESTIONS}),
            "modules": sorted({item["module"] for item in _MOCK_QUESTIONS if item["module"]}),
            "question_types": sorted({item["question_type"] for item in _MOCK_QUESTIONS if item["question_type"]}),
            "difficulties": sorted({item["difficulty"] for item in _MOCK_QUESTIONS if item["difficulty"]}),
            "statuses": sorted({item["status"] for item in _MOCK_QUESTIONS if item["status"]}),
            "topic1_ids": [],
            "topic1_values": [],
            "topic2_ids": [],
            "topic2_values": sorted({item["topic2"] for item in _MOCK_QUESTIONS if item["topic2"]}),
            "topic3_ids": [],
            "topic3_values": sorted({item["topic3"] for item in _MOCK_QUESTIONS if item["topic3"]}),
        }

    def _sqlite_facets(self) -> dict[str, Any]:
        with closing(self._get_connection()) as conn:
            years = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT year FROM papers WHERE year IS NOT NULL ORDER BY year DESC"
                ).fetchall()
            ]
            regions = _fetch_distinct(conn, "SELECT DISTINCT region FROM papers ORDER BY region")
            exam_types = _fetch_distinct(conn, "SELECT DISTINCT exam_type FROM papers ORDER BY exam_type")
            modules = _fetch_distinct(conn, "SELECT DISTINCT module FROM questions ORDER BY module")
            topic1_ids = _fetch_distinct(conn, "SELECT DISTINCT topic1_id FROM knowledge_points ORDER BY topic1_id")
            topic1_values = _fetch_distinct(conn, "SELECT DISTINCT topic1_name FROM knowledge_points ORDER BY topic1_name")
            topic2_ids = _fetch_distinct(conn, "SELECT DISTINCT topic2_id FROM knowledge_points ORDER BY topic2_id")
            topic2_values = _fetch_distinct(conn, "SELECT DISTINCT topic2 FROM questions ORDER BY topic2")
            topic3_ids = _fetch_distinct(conn, "SELECT DISTINCT topic3_id FROM knowledge_points ORDER BY topic3_id")
            topic3_values = _fetch_distinct(conn, "SELECT DISTINCT topic3 FROM questions ORDER BY topic3")
            difficulties = _fetch_distinct(conn, "SELECT DISTINCT CAST(difficulty AS TEXT) FROM questions WHERE difficulty IS NOT NULL ORDER BY difficulty")
            question_types = _fetch_distinct(conn, "SELECT DISTINCT question_type FROM questions ORDER BY question_type")
            statuses = _fetch_distinct(conn, "SELECT DISTINCT status FROM questions ORDER BY status")

        return {
            "years": years,
            "regions": regions,
            "exam_types": exam_types,
            "modules": modules,
            "question_types": question_types,
            "difficulties": difficulties,
            "statuses": statuses,
            "topic1_ids": topic1_ids,
            "topic1_values": topic1_values,
            "topic2_ids": topic2_ids,
            "topic2_values": topic2_values,
            "topic3_ids": topic3_ids,
            "topic3_values": topic3_values,
        }


def _fetch_distinct(conn: sqlite3.Connection, sql: str) -> list[str]:
    return [row[0] for row in conn.execute(sql).fetchall() if row[0] not in (None, "")]


def _build_fts_query(query: str) -> str:
    cleaned = query.strip().replace('"', '""')
    return f'"{cleaned}"'
