r"""Detect and repair mojibake (garbled Chinese text) in the SQLite database.

Common causes this script handles:
1. UTF-8 bytes stored as Latin-1  → re-encode as Latin-1, decode as UTF-8
2. Double-encoded UTF-8            → decode as Latin-1, re-encode as Latin-1,
                                      decode as UTF-8
3. Already-clean text              → left untouched (idempotent)

Usage:
    python scripts/maintenance/fix_legacy_encoding.py [--dry-run] [--db-path PATH]
"""

from __future__ import annotations

import argparse
import io
import os
import sys

# Ensure stdout supports UTF-8 on Windows GBK terminals
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
import json
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "data" / "app-db" / "physics_vault.sqlite3"

# ── columns to scan, grouped by table ──────────────────────────────

TEXT_COLUMNS: dict[str, list[str]] = {
    "questions": [
        "canonical_title",
        "module",
        "topic2",
        "topic3",
        "source",
        "vault_markdown_path",
    ],
    "question_text_index": [
        "stem_text",
        "stem_clean_text",
        "answer_text",
        "analysis_text",
        "tips_text",
        "options_json",
        "sub_questions_json",
        "figures_json",
        "tags_json",
        "title_text",
    ],
    "papers": [
        "paper_name",
        "notes",
    ],
    "knowledge_points": [
        "topic1_name",
        "topic2_name",
        "topic3_name",
        "source_chapter",
        "note",
    ],
    "image_assets": [
        "description",
        "extracted_text",
    ],
}


def is_clean_chinese(text: str) -> bool:
    """Return True if the text looks like healthy Chinese/ASCII content."""
    if not text:
        return True
    # Count problematic characters
    replacement = text.count("�")  # U+FFFD replacement char
    control_chars = sum(1 for ch in text if ord(ch) < 0x20 and ch not in "\t\n\r")
    total = len(text)
    if total == 0:
        return True
    # If >2% of chars are replacement chars, the text is garbled
    if replacement / total > 0.02:
        return False
    if control_chars > 0:
        return False
    return True


def try_recover(raw: bytes) -> str | None:
    """Attempt to recover Chinese text from garbled bytes.

    Returns the recovered string or None if recovery is impossible.
    """
    # Strategy 1: the bytes are already valid UTF-8 → nothing to do
    try:
        decoded = raw.decode("utf-8")
        if is_clean_chinese(decoded):
            return decoded  # already clean
    except UnicodeDecodeError:
        pass

    # Strategy 2: UTF-8 bytes were stored as Latin-1
    #   original UTF-8 bytes → stored as Latin-1 text → read back
    #   To recover: text.encode('latin-1').decode('utf-8')
    try:
        as_latin1 = raw.decode("latin-1")
        re_encoded = as_latin1.encode("latin-1")
        recovered = re_encoded.decode("utf-8")
        if is_clean_chinese(recovered) and _has_cjk(recovered):
            return recovered
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Strategy 3: Double Latin-1 wrapping
    try:
        as_latin1 = raw.decode("latin-1")
        re_encoded = as_latin1.encode("latin-1")
        as_latin1_2 = re_encoded.decode("latin-1")
        re_encoded_2 = as_latin1_2.encode("latin-1")
        recovered = re_encoded_2.decode("utf-8")
        if is_clean_chinese(recovered) and _has_cjk(recovered):
            return recovered
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    return None


def _has_cjk(text: str) -> bool:
    """True if text contains at least one CJK character."""
    return any("一" <= ch <= "鿿" for ch in text)


def fix_json_field(raw: bytes) -> bytes | None:
    """Repair a JSON-encoded text field (options_json, etc.).

    Returns the corrected bytes or None if no repair is needed.
    """
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Try Latin-1 recovery first
        recovered = try_recover(raw)
        if recovered is not None:
            decoded = recovered
        else:
            return None

    try:
        data = json.loads(decoded)
    except json.JSONDecodeError:
        return None

    changed = False
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key, val in item.items():
                    if isinstance(val, str):
                        recovered = try_recover(val.encode("utf-8"))
                        if recovered is not None and recovered != val:
                            item[key] = recovered
                            changed = True
    if changed:
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    return None


def fix_database(db_path: Path, dry_run: bool = False) -> dict[str, int]:
    """Scan and repair all text columns in the database.

    Returns a dict with repair statistics.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    stats = {"scanned": 0, "fixed": 0, "skipped": 0}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    for table, columns in TEXT_COLUMNS.items():
        # Check which columns actually exist
        existing = _existing_columns(conn, table, columns)
        if not existing:
            continue

        col_list = ", ".join(f"CAST({c} AS BLOB) as _{c}" for c in existing)
        pk = _primary_key(conn, table) or "rowid"

        try:
            rows = conn.execute(
                f"SELECT {pk}, {col_list} FROM {table}"
            ).fetchall()
        except sqlite3.OperationalError:
            continue

        for row in rows:
            row_id = row[pk]
            for col in existing:
                blob = row[f"_{col}"]
                if blob is None:
                    continue
                stats["scanned"] += 1

                # JSON fields get special treatment
                if col in ("options_json", "sub_questions_json",
                           "figures_json", "tags_json"):
                    repaired = fix_json_field(blob)
                    if repaired is not None:
                        stats["fixed"] += 1
                        if not dry_run:
                            conn.execute(
                                f"UPDATE {table} SET {col} = ? WHERE {pk} = ?",
                                (repaired.decode("utf-8"), row_id),
                            )
                    continue

                # Plain text fields
                try:
                    decoded = blob.decode("utf-8")
                except UnicodeDecodeError:
                    decoded = None

                if decoded is not None and is_clean_chinese(decoded):
                    continue  # already clean

                recovered = try_recover(blob)
                if recovered is not None and recovered != decoded:
                    stats["fixed"] += 1
                    if not dry_run:
                        conn.execute(
                            f"UPDATE {table} SET {col} = ? WHERE {pk} = ?",
                            (recovered, row_id),
                        )
                else:
                    stats["skipped"] += 1

    if not dry_run and stats["fixed"] > 0:
        conn.commit()

    conn.close()
    return stats


def _existing_columns(
    conn: sqlite3.Connection, table: str, candidates: list[str]
) -> list[str]:
    """Return the subset of *candidates* that actually exist in *table*."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in rows}
        return [c for c in candidates if c in existing]
    except sqlite3.OperationalError:
        return []


def _primary_key(conn: sqlite3.Connection, table: str) -> str | None:
    """Return the primary key column name for *table*, if any."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        for row in rows:
            if row["pk"]:
                return row["name"]
        return None
    except sqlite3.OperationalError:
        return None


# ── CLI ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="检测并修复 SQLite 数据库中的中文乱码字段"
    )
    p.add_argument(
        "--db-path",
        default=str(DEFAULT_DB),
        help=f"数据库路径 (默认: {DEFAULT_DB})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="仅检测，不实际修改数据库",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db_path)

    print(f"数据库: {db_path}")
    print(f"模式: {'预览' if args.dry_run else '修复'}")
    print()

    try:
        stats = fix_database(db_path, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"扫描字段数: {stats['scanned']}")
    print(f"修复数:     {stats['fixed']}")
    print(f"跳过数:     {stats['skipped']} (无法恢复)")

    if stats["fixed"] == 0:
        print("\n✓ 未发现乱码字段，数据库编码正常。")
    elif args.dry_run:
        print(f"\n! 预览模式: 发现 {stats['fixed']} 处可修复乱码，使用 --dry-run 以外的参数执行修复。")
    else:
        print(f"\n✓ 已修复 {stats['fixed']} 处乱码字段。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
