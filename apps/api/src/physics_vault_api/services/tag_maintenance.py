"""Autonomous maintenance helpers for question tags."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ..database import connect_db
from ..paths import default_db_path
from .embedding_refresh import schedule_question_embedding_refresh
from .metadata_management import MetadataManagementService
from .method_feature_index import refresh_question_method_features


MAX_TAG_MAINTENANCE_QUESTIONS = 500
MAX_TAGS_PER_QUESTION = 8
_TAG_SPLIT_RE = re.compile(r"[\s_\-:：/\\|]+")
_TAG_BRACKET_RE = re.compile(r"[()（）【】\[\]{}《》<>]")


def diagnose_tag_maintenance(
    *,
    query: str | None = None,
    limit: int = 50,
    min_similarity: float = 0.86,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Find near-duplicate tags and catalog tags that are unused."""

    path = Path(db_path) if db_path else default_db_path()
    rows, catalog = _load_tag_inventory(path, query=query)
    counts = Counter(tag for row in rows for tag in _parse_tags(row.get("tags_json")))
    tag_names = sorted(counts)
    groups: list[dict[str, Any]] = []
    used: set[str] = set()
    for tag in tag_names:
        if tag in used:
            continue
        similar = [
            other
            for other in tag_names
            if other != tag and other not in used and _tag_similarity(tag, other) >= min_similarity
        ]
        if not similar:
            continue
        members = [tag, *similar]
        canonical = _choose_canonical_tag(members, counts)
        aliases = [item for item in members if item != canonical]
        used.update(members)
        groups.append(
            {
                "canonical_tag": canonical,
                "aliases": aliases,
                "total_count": sum(counts[item] for item in members),
                "member_counts": [
                    {"tag": item, "count": counts[item]} for item in sorted(members)
                ],
                "suggested_action": "merge_aliases_into_canonical",
                "confidence": round(max(_tag_similarity(canonical, item) for item in aliases), 3),
            }
        )
        if len(groups) >= min(max(int(limit or 50), 1), 200):
            break

    unused_catalog_tags = [
        item
        for item in catalog
        if item["status"] == "active" and counts.get(item["tag_name"], 0) == 0
    ][: min(max(int(limit or 50), 1), 200)]
    return {
        "ok": True,
        "tag_count": len(tag_names),
        "question_count": len(rows),
        "near_duplicate_groups": groups,
        "unused_catalog_tags": unused_catalog_tags,
        "summary": {
            "near_duplicate_group_count": len(groups),
            "unused_catalog_tag_count": len(unused_catalog_tags),
        },
        "database_scope": "canonical_read_only",
    }


def suggest_question_tags(
    question_ids: list[str],
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Suggest high-confidence method and teaching tags from derived indexes."""

    clean_ids = _clean_question_ids(question_ids, max_count=MAX_TAG_MAINTENANCE_QUESTIONS)
    if not clean_ids:
        return _error("INVALID_ARGUMENT", "question_ids 至少需要一个题号。")
    path = Path(db_path) if db_path else default_db_path()
    placeholders = ",".join("?" for _ in clean_ids)
    with connect_db(path, writable=True) as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, qti.title_text, qti.stem_text,
                   qti.analysis_text, qti.tags_json
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            WHERE q.question_id IN ({placeholders})
            """,
            clean_ids,
        ).fetchall()
        method_rows = conn.execute(
            f"""
            SELECT question_id, branch, level, score, match_basis
            FROM question_method_features
            WHERE question_id IN ({placeholders})
              AND level IN ('explicit', 'structural')
            ORDER BY question_id, score DESC
            """,
            clean_ids,
        ).fetchall()
    methods_by_question: dict[str, list[dict[str, Any]]] = {}
    for row in method_rows:
        methods_by_question.setdefault(str(row["question_id"]), []).append(dict(row))

    items: list[dict[str, Any]] = []
    for row in rows:
        current = _parse_tags(row["tags_json"])
        suggestions: list[dict[str, Any]] = []
        for method in methods_by_question.get(str(row["question_id"]), []):
            branch = str(method["branch"])
            branch_tag = "重力配速法" if branch == "gravity" else "电场配速法"
            for tag in ("配速法", branch_tag):
                if tag not in current:
                    suggestions.append(
                        {
                            "tag": tag,
                            "source": "method_index",
                            "confidence": round(float(method["score"]), 3),
                            "reason": f"{method['level']} method match via {method['match_basis']}",
                        }
                    )
        text = " ".join(
            str(row[key] or "") for key in ("canonical_title", "title_text", "stem_text", "analysis_text")
        )
        if _looks_like_braking_trap(text) and "刹车陷阱" not in current:
            suggestions.append(
                {
                    "tag": "刹车陷阱",
                    "source": "content_rule",
                    "confidence": 0.82,
                    "reason": "题目同时出现刹车/停止语境和第 n 秒内运动量追问。",
                }
            )
        deduped: dict[str, dict[str, Any]] = {}
        for suggestion in suggestions:
            tag = str(suggestion["tag"])
            if tag not in deduped or float(suggestion["confidence"]) > float(deduped[tag]["confidence"]):
                deduped[tag] = suggestion
        recommended = [
            item
            for item in sorted(deduped.values(), key=lambda value: (-float(value["confidence"]), value["tag"]))
            if item["tag"] not in current
        ]
        items.append(
            {
                "question_id": str(row["question_id"]),
                "title": " ".join(str(row["title_text"] or row["canonical_title"] or "").split())[:120],
                "current_tags": current,
                "suggested_tags": recommended,
                "recommended_after_tags": _normalize_tags([*current, *(item["tag"] for item in recommended)])[:MAX_TAGS_PER_QUESTION],
            }
        )
    return {
        "ok": True,
        "items": items,
        "summary": {
            "question_count": len(items),
            "suggestion_count": sum(len(item["suggested_tags"]) for item in items),
        },
        "database_scope": "canonical_read_only",
    }


def maintain_question_tags(
    *,
    question_ids: list[str] | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    merge_map: dict[str, list[str]] | None = None,
    dry_run: bool = True,
    reason: str | None = None,
    create_catalog_tags: bool = True,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Preview or apply tag additions/removals and alias merges."""

    path = Path(db_path) if db_path else default_db_path()
    additions = _normalize_tags(add_tags or [])
    removals = {_tag_key(tag) for tag in _normalize_tags(remove_tags or [])}
    clean_merge_map = {
        _clean_tag(canonical): _normalize_tags(aliases)
        for canonical, aliases in (merge_map or {}).items()
        if _clean_tag(canonical) and _normalize_tags(aliases)
    }
    if not additions and not removals and not clean_merge_map:
        return _error("INVALID_ARGUMENT", "至少需要 add_tags、remove_tags 或 merge_map 之一。")
    if not dry_run and not str(reason or "").strip():
        return _error("INVALID_ARGUMENT", "写入标签维护结果时必须填写 reason。")

    clean_ids = _clean_question_ids(question_ids or [], max_count=MAX_TAG_MAINTENANCE_QUESTIONS)
    rows = _load_questions_for_tag_update(path, clean_ids, bool(clean_merge_map))
    updates: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for row in rows:
        before = _parse_tags(row.get("tags_json"))
        after = _apply_tag_rules(before, additions, removals, clean_merge_map)
        status = "unchanged" if before == after else "changed"
        if status == "changed":
            updates.append({"question_id": str(row["question_id"]), "tags": after})
        items.append(
            {
                "question_id": str(row["question_id"]),
                "title": row.get("title_text") or row.get("canonical_title"),
                "before_tags": before,
                "after_tags": after,
                "status": status,
            }
        )

    metadata_result: dict[str, Any] | None = None
    catalog_result: dict[str, Any] | None = None
    if not dry_run and updates:
        metadata_result = MetadataManagementService(path).batch_update_question_metadata(
            updates,
            reason=str(reason),
        )
        if create_catalog_tags:
            catalog_result = _maintain_tag_catalog(
                path,
                canonical_tags=[*additions, *clean_merge_map.keys()],
                aliases_by_canonical=clean_merge_map,
            )
        changed_ids = [item["question_id"] for item in updates]
        schedule_question_embedding_refresh(changed_ids, db_path=path)
        refresh_question_method_features(changed_ids, db_path=path)

    return {
        "ok": True,
        "dry_run": dry_run,
        "changed_count": len(updates),
        "items": items,
        "metadata_result": metadata_result,
        "catalog_result": catalog_result,
        "requires_confirmation": dry_run and bool(updates),
        "message": "预览完成，未写入数据库。" if dry_run else "已维护题目标签并刷新检索索引。",
        "database_scope": "canonical" if not dry_run else "canonical_preview",
    }


def _load_tag_inventory(path: Path, *, query: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clean_query = " ".join(str(query or "").split())
    params: list[Any] = []
    where = ""
    if clean_query:
        where = """
        WHERE qti.tags_json LIKE '%' || ? || '%'
           OR q.canonical_title LIKE '%' || ? || '%'
           OR qti.title_text LIKE '%' || ? || '%'
        """
        params.extend([clean_query, clean_query, clean_query])
    with connect_db(path, writable=True) as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, qti.title_text, qti.tags_json
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            {where}
            ORDER BY q.question_id
            """,
            params,
        ).fetchall()
        catalog = conn.execute(
            """
            SELECT tag_name, category, description, status
            FROM tag_catalog
            ORDER BY category, tag_name
            """
        ).fetchall()
    return [dict(row) for row in rows], [dict(row) for row in catalog]


def _load_questions_for_tag_update(path: Path, question_ids: list[str], allow_all_for_merge: bool) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if question_ids:
        where = f"WHERE q.question_id IN ({','.join('?' for _ in question_ids)})"
        params.extend(question_ids)
    elif not allow_all_for_merge:
        raise ValueError("question_ids 不能为空，除非提供 merge_map 做全库合并。")
    with connect_db(path, writable=True) as conn:
        rows = conn.execute(
            f"""
            SELECT q.question_id, q.canonical_title, qti.title_text, qti.tags_json
            FROM questions q
            LEFT JOIN question_text_index qti ON qti.question_id = q.question_id
            {where}
            ORDER BY q.question_id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _apply_tag_rules(
    tags: list[str],
    additions: list[str],
    removals: set[str],
    merge_map: dict[str, list[str]],
) -> list[str]:
    alias_to_canonical: dict[str, str] = {}
    for canonical, aliases in merge_map.items():
        alias_to_canonical[_tag_key(canonical)] = canonical
        for alias in aliases:
            alias_to_canonical[_tag_key(alias)] = canonical
    rewritten: list[str] = []
    for tag in tags:
        key = _tag_key(tag)
        if key in removals:
            continue
        rewritten.append(alias_to_canonical.get(key, tag))
    rewritten.extend(additions)
    return _normalize_tags(rewritten)[:MAX_TAGS_PER_QUESTION]


def _maintain_tag_catalog(
    path: Path,
    *,
    canonical_tags: list[str],
    aliases_by_canonical: dict[str, list[str]],
) -> dict[str, int]:
    canonical = _normalize_tags(canonical_tags)
    alias_rows = [(alias, canonical_tag) for canonical_tag, aliases in aliases_by_canonical.items() for alias in aliases]
    with connect_db(path, writable=True) as conn:
        inserted = 0
        merged = 0
        for tag in canonical:
            category = _tag_category(tag)
            before = conn.total_changes
            conn.execute(
                """
                INSERT INTO tag_catalog (tag_name, category, description, status, created_at, updated_at)
                VALUES (?, ?, 'AI maintained canonical tag', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(tag_name) DO UPDATE SET
                    status = 'active',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (tag, category),
            )
            inserted += int(conn.total_changes > before)
        for alias, canonical_tag in alias_rows:
            if _tag_key(alias) == _tag_key(canonical_tag):
                continue
            conn.execute(
                """
                INSERT INTO tag_catalog (tag_name, category, description, status, created_at, updated_at)
                VALUES (?, 'alias', ?, 'merged', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(tag_name) DO UPDATE SET
                    category = 'alias',
                    description = excluded.description,
                    status = 'merged',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (alias, f"Merged into {canonical_tag}"),
            )
            merged += 1
        conn.commit()
    return {"canonical_upserted": inserted, "aliases_marked_merged": merged}


def _choose_canonical_tag(tags: list[str], counts: Counter[str]) -> str:
    return sorted(tags, key=lambda tag: (-counts[tag], len(tag), tag))[0]


def _tag_similarity(left: str, right: str) -> float:
    lkey = _tag_key(left)
    rkey = _tag_key(right)
    if not lkey or not rkey:
        return 0.0
    if lkey == rkey:
        return 1.0
    if lkey in rkey or rkey in lkey:
        return 0.92
    return SequenceMatcher(None, lkey, rkey).ratio()


def _looks_like_braking_trap(text: str) -> bool:
    compact = _tag_key(text)
    has_brake = any(term in text for term in ("刹车", "制动", "停下", "停止", "末速度为0", "速度减为零"))
    has_nth_second = bool(re.search(r"第\s*\d+\s*s?\s*内|第\s*\d+\s*秒内", text, flags=re.I))
    has_kinematics = any(term in text for term in ("位移", "路程", "加速度", "匀减速"))
    return has_brake and has_nth_second and has_kinematics and "不停" not in compact


def _tag_category(tag: str) -> str:
    if any(term in tag for term in ("法", "陷阱", "模型", "技巧")):
        return "method"
    return "ai_generated"


def _clean_question_ids(question_ids: list[str], *, max_count: int) -> list[str]:
    clean = list(dict.fromkeys(str(item or "").strip() for item in question_ids if str(item or "").strip()))
    if len(clean) > max_count:
        raise ValueError(f"一次最多处理 {max_count} 道题。")
    return clean


def _parse_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return _normalize_tags(raw)
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
        return _normalize_tags(parsed)
    except (TypeError, json.JSONDecodeError):
        return _normalize_tags(str(raw).replace("，", ",").replace("、", ",").split(","))


def _normalize_tags(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else [value]
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        tag = _clean_tag(item)
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def _clean_tag(value: Any) -> str:
    tag = " ".join(str(value or "").strip().split())
    return tag[:30].strip()


def _tag_key(tag: str) -> str:
    value = _TAG_BRACKET_RE.sub("", str(tag or "")).casefold()
    value = _TAG_SPLIT_RE.sub("", value)
    return value.strip()


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error_info": {"code": code, "message": message}}
