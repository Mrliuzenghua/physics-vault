"""Check if Q4's image_filenames_json was corrupted by a previous PUT save."""
import json
import sqlite3
from pathlib import Path

DB = Path(r"C:\Users\lzh\OneDrive\Pysics Vault3.0\09-项目工程\physics-vault\data\app-db\physics_vault.sqlite3")
db = sqlite3.connect(str(DB))
db.row_factory = sqlite3.Row
cur = db.cursor()

# Check Q4 specifically
for qid in ["Q00000001", "Q00000004", "Q00000005"]:
    cur.execute("""
        SELECT question_id, image_count, image_filenames_json, image_asset_ids_json
        FROM question_text_index WHERE question_id = ?
    """, (qid,))
    r = cur.fetchone()
    if r:
        print(f"\n=== {r['question_id']} ===")
        print(f"  image_count = {r['image_count']}")
        filenames = json.loads(r['image_filenames_json'] or '[]')
        asset_ids = json.loads(r['image_asset_ids_json'] or '[]')
        print(f"  filenames = {filenames}")
        print(f"  asset_ids = {asset_ids}")
        # Check if any filename has the path prefix (corruption)
        for fn in filenames:
            if 'data/assets/questions/' in fn:
                print(f"  ⚠️ CORRUPTED: filename contains path prefix: {fn}")
    else:
        print(f"\n=== {qid} NOT FOUND ===")

# Also check image_assets table
print("\n=== image_assets table ===")
cur.execute("""
    SELECT asset_id, question_id, filename, file_path
    FROM image_assets WHERE question_id IN ('Q00000001','Q00000004','Q00000005')
    ORDER BY question_id
""")
for r in cur.fetchall():
    print(f"  {r['question_id']}: asset_id={r['asset_id']} filename={r['filename']} file_path={r['file_path']}")

db.close()
