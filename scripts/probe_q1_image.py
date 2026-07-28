#!/usr/bin/env python3
"""Probe Q1 image fields across DB, Detail API, Search API, and file serving."""
import urllib.request, json, sqlite3, os

DB = "data/app-db/physics_vault.sqlite3"

# 1. Database
print("=== Database (question_text_index) ===")
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
cur = db.cursor()
cur.execute("SELECT image_count, image_asset_ids_json, image_filenames_json FROM question_text_index WHERE question_id='Q00000001'")
r = cur.fetchone()
if r:
    print(f"  image_count = {r['image_count']}")
    print(f"  image_asset_ids_json = {r['image_asset_ids_json']}")
    print(f"  image_filenames_json = {r['image_filenames_json']}")

# image_assets table
print()
print("=== Database (image_assets + question_assets) ===")
cur.execute("SELECT * FROM image_assets WHERE question_id='Q00000001'")
for row in cur.fetchall():
    print(f"  image_assets: {dict(row)}")
cur.execute("SELECT * FROM question_assets WHERE question_id='Q00000001'")
for row in cur.fetchall():
    print(f"  question_assets: {dict(row)}")

# 2. Detail API
print()
print("=== Detail API (/questions/Q00000001) ===")
res = urllib.request.urlopen("http://127.0.0.1:8000/questions/Q00000001")
data = json.loads(res.read())
for k in ["image_count", "image_filenames", "image_asset_ids", "image_filenames_json", "image_asset_ids_json", "figures"]:
    print(f"  {k} = {data.get(k, '<MISSING>')}")

# 3. Search API
print()
print("=== Search API (/search/questions?limit=5) ===")
res2 = urllib.request.urlopen("http://127.0.0.1:8000/search/questions?limit=5")
data2 = json.loads(res2.read())
items = data2.get("items", data2) if isinstance(data2, dict) else data2
q1 = next((q for q in items if q.get("question_id") == "Q00000001"), None)
if q1:
    for k in ["image_count", "image_filenames", "image_asset_ids", "figures", "has_media"]:
        print(f"  {k} = {q1.get(k, '<MISSING>')}")
    print(f"  all keys = {list(q1.keys())}")
else:
    print("  Q1 not found in search results")

# 4. File serving
print()
print("=== File serving ===")
fn = json.loads(r["image_filenames_json"]) if r and r["image_filenames_json"] else []
for fname in fn:
    url = f"http://127.0.0.1:8000/files/data/assets/questions/{fname}"
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        print(f"  OK {resp.status} {fname} ({len(resp.read())} bytes)")
    except Exception as e:
        print(f"  FAIL {fname} -> {e}")
    # Also check disk
    disk_path = f"data/assets/questions/{fname}"
    print(f"  disk: {disk_path} exists={os.path.exists(disk_path)} size={os.path.getsize(disk_path) if os.path.exists(disk_path) else 0}")
