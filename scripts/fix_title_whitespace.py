#!/usr/bin/env python3
"""修复 canonical_title 中的多余空白/换行"""
import sqlite3, re, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute("SELECT question_id, canonical_title FROM questions ORDER BY question_id")
for r in cur.fetchall():
    title = r["canonical_title"] or ""
    # 压缩多余空白和换行
    cleaned = re.sub(r'\n{2,}', '\n', title)
    cleaned = re.sub(r' {2,}', ' ', cleaned)
    cleaned = cleaned.strip()
    if cleaned != title:
        cur.execute("UPDATE questions SET canonical_title = ?, updated_at = datetime('now') WHERE question_id = ?",
                     (cleaned, r["question_id"]))
        print(f"[{r['question_id']}] {repr(title[:40])} → {repr(cleaned[:40])}")

db.commit()
db.close()
print("Done")
