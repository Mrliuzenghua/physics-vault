"""Business logic for batch question writing.

Responsibilities:
- Validate incoming question records
- Normalise / default-fill missing fields
- Serialise list-type fields to JSON strings
- Build derived text fields (stem_text, canonical_title)
- Delegate the actual database writes to QuestionWriteRepository
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..repositories.question_write import QuestionWriteRepository
from ..schemas.question_write import QuestionBatchWriteResult, QuestionRecord

logger = logging.getLogger(__name__)


def _build_canonical_title(title: str, max_len: int = 100) -> str:
    """Create a compact title without cutting through inline LaTeX."""

    cleaned = " ".join(
        line.strip()
        for line in title.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip() and not line.strip().startswith("![fig:")
    ).strip()
    if len(cleaned) <= max_len:
        return cleaned or "Imported question"

    clipped = cleaned[:max_len]
    if clipped.count("$") % 2 == 1:
        last_math_start = clipped.rfind("$")
        if last_math_start > 20:
            clipped = clipped[:last_math_start]

    clipped = clipped.rstrip("，。；、,.;:： （(").strip()
    return clipped or cleaned[:max_len].strip() or "Imported question"


class QuestionWriteService:
    """Batch-write questions into the SQLite database with validation.

    This service is intentionally **not** coupled to any particular
    upstream source (review workbench, import pipeline, migration
    scripts).  Any caller that can produce a list of ``QuestionRecord``
    or compatible dicts can use this service.
    """

    def __init__(self, repository: QuestionWriteRepository | None = None) -> None:
        self._repo = repository or QuestionWriteRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_batch(
        self,
        questions: list[dict[str, Any]],
    ) -> QuestionBatchWriteResult:
        """Validate, normalise and persist a batch of questions.

        Returns a ``QuestionBatchWriteResult`` with counts and any
        validation errors encountered.
        """
        errors: list[str] = []
        valid: list[QuestionRecord] = []

        for i, raw in enumerate(questions):
            try:
                record = self._validate_and_normalise(raw, i)
                valid.append(record)
            except ValueError as exc:
                errors.append(str(exc))

        if not valid:
            return QuestionBatchWriteResult(
                received_count=len(questions),
                saved_count=0,
                errors=errors,
            )

        # Serialise to repo-compatible dicts
        rows = [self._to_repo_row(r) for r in valid]

        try:
            counts = self._repo.upsert_many(rows)
        except FileNotFoundError:
            return QuestionBatchWriteResult(
                received_count=len(questions),
                saved_count=0,
                errors=["数据库文件不存在，写入失败"] + errors,
            )
        except Exception as exc:
            logger.exception("Batch upsert failed")
            return QuestionBatchWriteResult(
                received_count=len(questions),
                saved_count=0,
                errors=[f"数据库写入异常: {exc}"] + errors,
            )

        return QuestionBatchWriteResult(
            received_count=len(questions),
            saved_count=counts["saved"],
            inserted_count=counts["inserted"],
            updated_count=counts["updated"],
            errors=errors,
        )

    def delete_batch(self, question_ids: list[str]) -> dict[str, Any]:
        """Delete a batch of questions from the database."""

        try:
            return self._repo.delete_many(question_ids)
        except FileNotFoundError:
            return {
                "requested": len(question_ids),
                "deleted": 0,
                "missing_ids": question_ids,
                "error": "数据库文件不存在，删除失败",
            }

    def return_to_review(
        self,
        question_id: str,
        reason: str | None = None,
        reviewer: str | None = None,
    ) -> dict[str, Any]:
        """Return one live question to the review queue for rework."""

        try:
            return self._repo.return_to_review(question_id, reason=reason, reviewer=reviewer)
        except FileNotFoundError:
            return {
                "question_id": question_id,
                "review_id": None,
                "status": "missing",
                "error": "数据库文件不存在，无法送回校对中心",
            }

    # ------------------------------------------------------------------
    # Validation & normalisation
    # ------------------------------------------------------------------

    def _validate_and_normalise(
        self, raw: dict[str, Any], index: int
    ) -> QuestionRecord:
        prefix = f"第{index + 1}题" if raw.get("question_id") else f"题目[{index}]"

        question_id = raw.get("question_id")
        if not question_id or not str(question_id).strip():
            raise ValueError(f"{prefix}: question_id 不能为空")

        title = raw.get("title")
        if not title or not str(title).strip():
            raise ValueError(f"{prefix} ({question_id}): title 不能为空")

        question_type = raw.get("question_type")
        if not question_type or not str(question_type).strip():
            raise ValueError(f"{prefix} ({question_id}): question_type 不能为空")

        # Normalise difficulty
        difficulty = raw.get("difficulty")
        if difficulty is not None:
            try:
                difficulty = int(difficulty)
                if difficulty == 0:
                    difficulty = None
                elif difficulty < 1 or difficulty > 5:
                    raise ValueError(
                        f"{prefix} ({question_id}): difficulty 必须在 1-5 之间，当前值 {difficulty}"
                    )
            except (TypeError, ValueError):
                raise ValueError(
                    f"{prefix} ({question_id}): difficulty 必须是 1-5 的整数"
                )

        source_page = raw.get("source_page")
        if source_page is not None:
            try:
                source_page = int(source_page)
                if source_page < 1:
                    raise ValueError(
                        f"{prefix} ({question_id}): source_page 必须是正整数"
                    )
            except (TypeError, ValueError):
                raise ValueError(
                    f"{prefix} ({question_id}): source_page 必须是正整数"
                )

        # Ensure list fields are lists
        options = raw.get("options") or []
        if not isinstance(options, list):
            raise ValueError(f"{prefix} ({question_id}): options 必须是数组")

        sub_questions = raw.get("sub_questions") or []
        if not isinstance(sub_questions, list):
            raise ValueError(f"{prefix} ({question_id}): sub_questions 必须是数组")

        figures = raw.get("figures") or []
        if not isinstance(figures, list):
            raise ValueError(f"{prefix} ({question_id}): figures 必须是数组")

        tags = raw.get("tags") or []
        if not isinstance(tags, list):
            raise ValueError(f"{prefix} ({question_id}): tags 必须是数组")

        return QuestionRecord(
            question_id=str(question_id).strip(),
            question_type=str(question_type).strip(),
            title=str(title).strip(),
            options=options,
            answer=str(raw.get("answer") or "").strip(),
            analysis=str(raw.get("analysis") or "").strip(),
            sub_questions=sub_questions,
            figures=figures,
            difficulty=difficulty,
            knowledge_point=str(raw.get("knowledge_point") or "").strip(),
            tags=[str(t) for t in tags if t],
            source=str(raw.get("source") or "").strip(),
            source_raw=str(raw.get("source_raw") or raw.get("source") or "").strip(),
            import_batch_id=raw.get("import_batch_id"),
            source_page=source_page,
            source_region_id=str(raw.get("source_region_id") or "").strip() or None,
            raw_text=str(raw.get("raw_text") or "").strip() or None,
            review_status=str(raw.get("review_status") or "confirmed"),
        )

    # ------------------------------------------------------------------
    # Serialisation for the repository
    # ------------------------------------------------------------------

    def _to_repo_row(self, record: QuestionRecord) -> dict[str, Any]:
        """Convert a validated QuestionRecord into the flat dict the
        repository expects, with JSON-encoded list fields and derived
        text fields."""

        options_json = json.dumps(record.options or [], ensure_ascii=False)
        sub_questions_json = json.dumps(record.sub_questions or [], ensure_ascii=False)
        figures_json = json.dumps(record.figures or [], ensure_ascii=False)
        tags_json = json.dumps(record.tags or [], ensure_ascii=False)

        # Extract just the filename from local_path to prevent storing
        # full path prefixes that cause double-path rendering issues.
        def _extract_filename(path_or_name: str) -> str:
            if not path_or_name:
                return ""
            for sep in ('/', '\\'):
                if sep in path_or_name:
                    path_or_name = path_or_name.rsplit(sep, 1)[-1]
            return path_or_name

        image_asset_ids = [
            f.get("fig_uuid", f.get("asset_id", "")) for f in record.figures
        ]
        image_filenames = [
            _extract_filename(f.get("local_path", f.get("filename", ""))) for f in record.figures
        ]
        image_count = len(record.figures)

        # Build stem_text from title + options + sub_questions + answer + analysis
        text_parts: list[str] = [record.title]
        for opt in record.options:
            label = opt.get("opt", opt.get("label", ""))
            text = opt.get("content", opt.get("text", ""))
            text_parts.append(f"{label}. {text}" if label else text)
        for sq in record.sub_questions:
            sq_id = sq.get("sub_id", sq.get("index", ""))
            sq_title = sq.get("title", sq.get("stem", ""))
            text_parts.append(f"（{sq_id}）{sq_title}" if sq_id else sq_title)
        if record.answer:
            text_parts.append(f"【答案】{record.answer}")
        if record.analysis:
            text_parts.append(f"【解析】{record.analysis}")
        stem_text = "\n".join(text_parts)

        canonical_title = _build_canonical_title(record.title)

        return {
            "question_id": record.question_id,
            "canonical_title": canonical_title,
            "question_type": record.question_type,
            "status": "已审核",
            "difficulty": record.difficulty if record.difficulty is not None else 0,
            "knowledge_point": record.knowledge_point or None,
            "import_batch_id": record.import_batch_id,
            "options_json": options_json,
            "sub_questions_json": sub_questions_json,
            "figures_json": figures_json,
            "image_asset_ids_json": json.dumps(image_asset_ids or [], ensure_ascii=False),
            "image_filenames_json": json.dumps(image_filenames or [], ensure_ascii=False),
            "image_count": image_count,
            "tags_json": tags_json,
            "stem_text": stem_text,
            "title_text": record.title,
            "stem_clean_text": record.raw_text,
            "answer_text": record.answer or None,
            "analysis_text": record.analysis or None,
            "content_hash": None,
            "schema_version": "v2",
            "primary_question_no": None,
            "source_id": None,
            "source_region_id": record.source_region_id,
            "source": record.source or None,
            "source_text": record.source_raw or record.source or None,
            "source_page": record.source_page,
            "vault_markdown_path": f"import/{record.question_id}.md",
        }
