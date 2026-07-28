#!/usr/bin/env python3
"""探查 image_assets 和 question_assets 表"""
import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()

# image_assets schema
print("=== image_assets schema ===")
cur.execute("PRAGMA table_info(image_assets)")
for r in cur.fetchall():
    print(f"  {r['name']:30s} {r['type']:20s}")

print("\n=== question_assets schema ===")
cur.execute("PRAGMA table_info(question_assets)")
for r in cur.fetchall():
    print(f"  {r['name']:30s} {r['type']:20s}")

# Check which questions have image_assets but image_count=0 in text_index
print("\n=== Questions with image_assets but image_count=0 ===")
cur.execute("""
    SELECT q.question_id, qti.image_count, qti.image_filenames_json,
           GROUP_CONCAT(ia.filename, '||') as filenames,
           GROUP_CONCAT(ia.asset_id, '||') as asset_ids,
           COUNT(*) as actual_count
    FROM question_assets qa
    JOIN image_assets ia ON qa.asset_id = ia.asset_id
    JOIN questions q ON q.question_id = qa.question_id
    JOIN question_text_index qti ON qti.question_id = q.question_id
    GROUP BY q.question_id
    ORDER BY q.question_id
""")
for r in cur.fetchall():
    print(f"  [{r['question_id']}] db_count={r['image_count']} actual={r['actual_count']}")
    print(f"    filenames: {r['filenames']}")
    print(f"    asset_ids: {r['asset_ids']}")
    print(f"    qti_filenames: {r['image_filenames_json']}")
    print()

db.close()
