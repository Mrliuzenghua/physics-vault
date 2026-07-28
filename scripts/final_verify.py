#!/usr/bin/env python3
"""最终验证：所有12条数据清洗后状态"""
import sqlite3, json, os, re

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute("""
    SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty,
           ti.title_text, ti.stem_clean_text, ti.options_json,
           ti.answer_text, ti.analysis_text, ti.tips_text,
           ti.image_count, ti.image_filenames_json, ti.tags_json,
           length(ti.stem_text) as stem_len
    FROM questions q
    JOIN question_text_index ti ON q.question_id = ti.question_id
    ORDER BY q.question_id
""")

rows = cur.fetchall()
print(f"{'='*72}")
print(f"   数据库清洗后验证报告 - {len(rows)} 条数据")
print(f"{'='*72}\n")

all_ok = True
for r in rows:
    qid = r["question_id"]
    opts = json.loads(r["options_json"] or "[]")
    img_names = json.loads(r["image_filenames_json"] or "[]")
    answer = r["answer_text"] or ""
    title = r["canonical_title"] or ""
    
    # 检查项
    opt_format_ok = all("opt" in o and "content" in o and set(o.keys()) == {"opt", "content"} for o in opts) if opts else True
    answer_ok = "{{img" not in answer
    img_synced = r["image_count"] == len(img_names)
    title_ok = not re.match(r'^\d+[\.．]', title) and not re.match(r'^第\d+题$', title)
    title_clean = not bool(re.search(r'\n{2,}', title))
    
    issues = []
    if not opt_format_ok: issues.append("options格式")
    if not answer_ok: issues.append("answer占位符")
    if not img_synced: issues.append("图片不同步")
    if not title_ok: issues.append("title有前缀")
    if not title_clean: issues.append("title有多余换行")
    
    status = "✅" if not issues else "❌"
    if issues:
        all_ok = False
    
    qtype_map = {"single_choice": "单选", "multi_choice": "多选", "calculation": "计算", "experiment": "实验"}
    qtype = qtype_map.get(r["question_type"], r["question_type"])
    
    print(f"{status} [{qid}] {qtype} 难度{r['difficulty']} | {len(opts)}选项 | {r['image_count']}图 | stem={r['stem_len']}字")
    if title:
        print(f"   标题: {title[:70]}{'...' if len(title)>70 else ''}")
    if opts:
        first_opt = opts[0]
        print(f"   选项[0]: {first_opt['opt']}. {first_opt['content'][:50]}{'...' if len(first_opt['content'])>50 else ''}")
    if answer:
        print(f"   答案: {answer[:50]}{'...' if len(answer)>50 else ''}")
    if img_names:
        print(f"   图片: {img_names[0]}{' (+{} more)'.format(len(img_names)-1) if len(img_names)>1 else ''}")
    if issues:
        print(f"   ⚠️ 问题: {', '.join(issues)}")
    print()

print(f"\n{'='*72}")
print(f"{'全部通过' if all_ok else '有问题'}")

db.close()
