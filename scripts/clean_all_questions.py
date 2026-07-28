#!/usr/bin/env python3
"""
清洗 physics_vault 数据库中全部12条历史题目数据。

清洗项：
1. options_json 格式统一为 {opt: "A", content: "..."}
2. canonical_title 用 stem_clean_text[:80] 替换（去掉题号前缀/"第X题"）
3. answer_text 清理 {{imgXX}} 占位符
4. image_count/image_asset_ids_json/image_filenames_json 从 question_assets+image_assets 同步
5. stem_text 从干净组件重建（题干 + 选项 + 答案 + 解析）
6. title_text 保留原样（"第X题"标签）
"""
import sqlite3
import json
import re
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")


def normalize_option(opt: dict) -> dict:
    """将选项统一为 {opt: "A", content: "..."} 格式"""
    label = opt.get("opt", opt.get("label", ""))
    content = opt.get("content", opt.get("text", ""))
    return {"opt": label, "content": content}


def normalize_options(options_json: str) -> list:
    """标准化 options_json"""
    try:
        opts = json.loads(options_json) if options_json else []
    except (json.JSONDecodeError, TypeError):
        return []
    return [normalize_option(o) for o in opts]


def clean_answer_text(text: str) -> str:
    """清理 answer_text 中的 {{imgXX}} 占位符"""
    if not text:
        return text
    # 替换 {{img01}} 等占位符为 [图] 或直接移除
    cleaned = re.sub(r'\{\{img\d+\}\}', '', text)
    # 清理多余空格
    cleaned = re.sub(r'  +', ' ', cleaned)
    return cleaned.strip()


def build_canonical_title(stem_clean: str) -> str:
    """从 stem_clean_text 生成干净的 canonical_title"""
    if not stem_clean:
        return "导入题"
    # 去掉 {{imgXX}} 占位符
    title = re.sub(r'\{\{img\d+\}\}', '', stem_clean).strip()
    # 去掉开头的题号前缀（如 "4．" "第4题"）
    title = re.sub(r'^\d+[\.\．]\s*', '', title)
    title = re.sub(r'^第\d+题\s*', '', title)
    # 截取前80字符（不截断到半个中文）
    if len(title) > 80:
        title = title[:80]
    return title.strip() or "导入题"


def build_stem_text(stem_clean: str, options: list, answer: str, analysis: str) -> str:
    """从干净组件重建 stem_text（全量快照）"""
    parts = []
    # 题干（保留 {{imgXX}} 占位符，它们在渲染时会被替换为图片）
    if stem_clean:
        parts.append(stem_clean.strip())
    # 选项
    for opt in options:
        label = opt.get("opt", "")
        content = opt.get("content", "")
        if label:
            parts.append(f"{label}. {content}")
        else:
            parts.append(content)
    # 答案
    if answer:
        parts.append(f"【答案】{answer}")
    # 解析
    if analysis:
        parts.append(f"【解析】{analysis}")
    return "\n".join(parts)


def get_image_links(db, question_id: str) -> tuple:
    """从 question_assets + image_assets 获取图片关联"""
    cur = db.cursor()
    cur.execute("""
        SELECT ia.asset_id, ia.filename
        FROM question_assets qa
        JOIN image_assets ia ON qa.asset_id = ia.asset_id
        WHERE qa.question_id = ?
        ORDER BY qa.sort_order
    """, (question_id,))
    rows = cur.fetchall()
    asset_ids = [r[0] for r in rows]
    filenames = [r[1] for r in rows]
    return asset_ids, filenames


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # 获取所有题目数据
    cur.execute("""
        SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty,
               ti.title_text, ti.stem_text, ti.stem_clean_text,
               ti.options_json, ti.answer_text, ti.analysis_text, ti.tips_text,
               ti.image_count, ti.image_asset_ids_json, ti.image_filenames_json,
               ti.tags_json
        FROM questions q
        JOIN question_text_index ti ON q.question_id = ti.question_id
        ORDER BY q.question_id
    """)
    rows = cur.fetchall()

    print(f"=== 开始清洗 {len(rows)} 条数据 ===\n")

    changes_log = []
    for r in rows:
        qid = r["question_id"]
        changes = []

        # --- 1. 标准化 options_json ---
        old_opts = r["options_json"] or "[]"
        new_opts_list = normalize_options(old_opts)
        new_opts_json = json.dumps(new_opts_list, ensure_ascii=False)

        opts_changed = False
        try:
            old_opts_list = json.loads(old_opts)
            # 检查是否需要变更
            for o in old_opts_list:
                if "opt" not in o or "content" not in o:
                    opts_changed = True
                    break
                # 检查是否有冗余字段
                if set(o.keys()) - {"opt", "content"}:
                    opts_changed = True
                    break
        except:
            opts_changed = True

        if opts_changed:
            changes.append(f"options_json: {len(json.loads(old_opts))}项格式标准化")
            # 更新 DB
            cur.execute(
                "UPDATE question_text_index SET options_json = ?, updated_at = datetime('now') WHERE question_id = ?",
                (new_opts_json, qid)
            )

        # --- 2. 清理 answer_text ---
        old_answer = r["answer_text"] or ""
        new_answer = clean_answer_text(old_answer)
        if new_answer != old_answer:
            changes.append(f"answer_text: 清理 {{img}} 占位符")
            cur.execute(
                "UPDATE question_text_index SET answer_text = ?, updated_at = datetime('now') WHERE question_id = ?",
                (new_answer, qid)
            )

        # --- 3. 同步图片字段 ---
        asset_ids, filenames = get_image_links(db, qid)
        old_img_count = r["image_count"]
        new_img_count = len(filenames)
        old_filenames_json = r["image_filenames_json"] or "[]"
        new_filenames_json_val = json.dumps(filenames, ensure_ascii=False)
        new_asset_ids_json_val = json.dumps(asset_ids, ensure_ascii=False)

        try:
            old_filenames_list = json.loads(old_filenames_json)
        except:
            old_filenames_list = []

        if old_img_count != new_img_count or old_filenames_list != filenames:
            changes.append(f"image: count {old_img_count}→{new_img_count}, filenames同步")
            cur.execute(
                """UPDATE question_text_index
                   SET image_count = ?, image_asset_ids_json = ?, image_filenames_json = ?,
                       updated_at = datetime('now')
                   WHERE question_id = ?""",
                (new_img_count, new_asset_ids_json_val, new_filenames_json_val, qid)
            )

        # --- 4. 更新 canonical_title ---
        stem_clean = r["stem_clean_text"] or ""
        new_title = build_canonical_title(stem_clean)
        old_title = r["canonical_title"] or ""
        if new_title != old_title and new_title:
            changes.append(f"canonical_title: '{old_title[:40]}' → '{new_title[:40]}'")
            cur.execute(
                "UPDATE questions SET canonical_title = ?, updated_at = datetime('now') WHERE question_id = ?",
                (new_title, qid)
            )

        # --- 5. 重建 stem_text ---
        # 重新读取可能已更新的字段
        cur.execute("""
            SELECT stem_clean_text, options_json, answer_text, analysis_text
            FROM question_text_index WHERE question_id = ?
        """, (qid,))
        fresh = cur.fetchone()
        new_stem = build_stem_text(
            fresh["stem_clean_text"] or "",
            json.loads(fresh["options_json"] or "[]"),
            fresh["answer_text"] or "",
            fresh["analysis_text"] or ""
        )
        old_stem = r["stem_text"] or ""
        if new_stem != old_stem:
            changes.append(f"stem_text: 重建（{len(old_stem)}→{len(new_stem)}字符）")
            cur.execute(
                "UPDATE question_text_index SET stem_text = ?, updated_at = datetime('now') WHERE question_id = ?",
                (new_stem, qid)
            )

        # --- 记录变更 ---
        if changes:
            print(f"[{qid}] ✅ {len(changes)}项变更:")
            for c in changes:
                print(f"    - {c}")
            changes_log.append({"qid": qid, "changes": changes})
        else:
            print(f"[{qid}] ⏭ 无变更")
        print()

    # 提交
    db.commit()
    print(f"\n=== 清洗完成 ===")
    print(f"总计: {len(rows)} 条, {len(changes_log)} 条有变更")

    # 验证
    print(f"\n=== 验证 ===")
    cur.execute("""
        SELECT q.question_id, q.canonical_title,
               ti.options_json, ti.answer_text, ti.image_count,
               ti.image_filenames_json, length(ti.stem_text) as stem_len
        FROM questions q
        JOIN question_text_index ti ON q.question_id = ti.question_id
        ORDER BY q.question_id
    """)
    for r in cur.fetchall():
        opts = json.loads(r["options_json"] or "[]")
        opt_ok = all("opt" in o and "content" in o and len(o) == 2 for o in opts) if opts else True
        answer_ok = "{{img" not in (r["answer_text"] or "")
        img_count = r["image_count"]
        filenames = json.loads(r["image_filenames_json"] or "[]")
        img_synced = img_count == len(filenames)
        title_ok = not r["canonical_title"].startswith(("第", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")) or r["canonical_title"].startswith("第")
        # 实际检查 canonical_title 不含题号前缀
        ct = r["canonical_title"] or ""
        title_clean = not re.match(r'^\d+[\.．]', ct) and not re.match(r'^第\d+题$', ct)

        status = "✅" if (opt_ok and answer_ok and img_synced and title_clean) else "❌"
        issues = []
        if not opt_ok: issues.append("options格式")
        if not answer_ok: issues.append("answer有占位符")
        if not img_synced: issues.append("图片不同步")
        if not title_clean: issues.append("title有前缀")
        print(f"  [{r['question_id']}] {status} opts={len(opts)} answer_ok={answer_ok} img={img_count}/{len(filenames)} stem={r['stem_len']}ch {', '.join(issues) if issues else 'OK'}")

    db.close()


if __name__ == "__main__":
    main()
