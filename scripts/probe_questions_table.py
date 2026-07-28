#!/usr/bin/env python3
"""探查 questions 表和 question_text_index 表的对照"""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute("""
    SELECT q.question_id, q.canonical_title, q.question_type, q.difficulty,
           q.status, q.review_status, q.primary_paper_id, q.primary_question_no,
           ti.title_text, ti.stem_clean_text, ti.source_text
    FROM questions q
    LEFT JOIN question_text_index ti ON q.question_id = ti.question_id
    ORDER BY q.question_id
""")

for r in cur.fetchall():
    print(f"[{r['question_id']}] type={r['question_type']!r} diff={r['difficulty']!r} status={r['status']!r}")
    print(f"  canonical_title  = {repr(r['canonical_title'])[:120]}")
    print(f"  title_text       = {repr(r['title_text'])[:80]}")
    print(f"  stem_clean(前80) = {repr(r['stem_clean_text'])[:80]}")
    print(f"  source_text      = {repr(r['source_text'])[:60]}")
    print(f"  paper={r['primary_paper_id']!r} qno={r['primary_question_no']!r}")
    print()
db.close()
