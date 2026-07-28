#!/usr/bin/env python3
"""探查所有题目的当前字段状态，找出错位情况"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")

db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute("""
    SELECT question_id, title_text, stem_text, stem_clean_text,
           options_json, answer_text, analysis_text, tips_text,
           source_text, source_id, paper_id, question_no,
           image_count, image_asset_ids_json, image_filenames_json,
           tags_json
    FROM question_text_index
    ORDER BY question_id
""")

rows = cur.fetchall()
print(f"=== 共 {len(rows)} 条题目 ===\n")

for r in rows:
    qid = r["question_id"]
    opts = r["options_json"]
    try:
        opts_parsed = json.loads(opts) if opts else []
    except:
        opts_parsed = f"(parse error: {opts!r})"
    print(f"{'='*80}")
    print(f"[{qid}]  paper={r['paper_id']!r}  qno={r['question_no']!r}  src={r['source_text']!r}  src_id={r['source_id']!r}")
    print(f"  title_text    = {repr(r['title_text'])[:150]}")
    print(f"  stem_clean    = {repr(r['stem_clean_text'])[:150]}")
    print(f"  options_json  = {repr(opts)}[:80]  -> parsed: {opts_parsed if isinstance(opts_parsed, str) else f'[{len(opts_parsed)} items]'}")
    print(f"  answer_text   = {repr(r['answer_text'])[:120]}")
    print(f"  analysis_text = {repr(r['analysis_text'])[:120]}")
    print(f"  tips_text     = {repr(r['tips_text'])[:80]}")
    print(f"  tags_json     = {repr(r['tags_json'])[:80]}")
    print(f"  image_count   = {r['image_count']}  filenames={repr(r['image_filenames_json'])[:60]}")
    print(f"  stem_text(前400字) = {repr(r['stem_text'])[:400]}")
    print()

db.close()
