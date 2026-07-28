"""Fix corrupted image_filenames_json in question_text_index.

When a question was saved via the detail page PUT endpoint, the frontend's
normalizeQuestion set local_path = 'data/assets/questions/filename.png',
and the backend's _to_repo_row used that full path as the filename.
This strips the path prefix to restore correct filenames.
"""
import json
import sqlite3
from pathlib import Path

DB = Path(r"C:\Users\lzh\OneDrive\Pysics Vault3.0\09-项目工程\physics-vault\data\app-db\physics_vault.sqlite3")
db = sqlite3.connect(str(DB))
db.row_factory = sqlite3.Row
cur = db.cursor()

# Find all questions with corrupted filenames
cur.execute("SELECT question_id, image_filenames_json FROM question_text_index WHERE image_filenames_json LIKE '%data/assets/questions/%'")
corrupted = cur.fetchall()

print(f"Found {len(corrupted)} corrupted rows")
fixed = 0
for r in corrupted:
    filenames = json.loads(r['image_filenames_json'])
    fixed_filenames = []
    for fn in filenames:
        if 'data/assets/questions/' in fn:
            clean = fn.split('data/assets/questions/')[-1]
            fixed_filenames.append(clean)
            print(f"  {r['question_id']}: '{fn}' -> '{clean}'")
        else:
            fixed_filenames.append(fn)
    
    new_json = json.dumps(fixed_filenames, ensure_ascii=False)
    cur.execute(
        "UPDATE question_text_index SET image_filenames_json = ? WHERE question_id = ?",
        (new_json, r['question_id'])
    )
    fixed += 1
    print(f"  ✅ Updated {r['question_id']}")

db.commit()
print(f"\nFixed {fixed} rows")

# Verify
cur.execute("SELECT question_id, image_filenames_json FROM question_text_index WHERE image_filenames_json LIKE '%data/assets/questions/%'")
remaining = cur.fetchall()
print(f"Remaining corrupted: {len(remaining)}")

db.close()
