import sqlite3, json, os

db = sqlite3.connect('data/app-db/physics_vault.sqlite3')
db.row_factory = sqlite3.Row
cur = db.cursor()

# 1. image_assets 实际内容
print('=== image_assets (all 17) ===')
cur.execute('SELECT asset_id, filename, file_path, paper_id, question_id, image_type, binding_confidence, verified, mime_type, width, height FROM image_assets ORDER BY asset_id')
for r in cur.fetchall():
    exists = ''
    fp = r['file_path']
    if fp:
        exists = 'FILE_EXISTS' if os.path.exists(fp) else 'FILE_MISSING'
    print(f"  {r['asset_id']} | q={r['question_id']} | type={r['image_type']} | conf={r['binding_confidence']} | verified={r['verified']} | {exists}")
    print(f"    filename={r['filename']}")
    print(f"    path={fp}")

# 2. question_assets 关联
print()
print('=== question_assets (all 17) ===')
cur.execute('SELECT link_id, question_id, asset_id, role, sort_order, placeholder_key, is_primary, is_verified FROM question_assets ORDER BY question_id, sort_order')
for r in cur.fetchall():
    print(f"  q={r['question_id']} asset={r['asset_id']} role={r['role']} sort={r['sort_order']} primary={r['is_primary']} verified={r['is_verified']} placeholder={r['placeholder_key']}")

# 3. 每题的图片关联完整视图
print()
print('=== PER-QUESTION image status ===')
cur.execute("""
    SELECT q.question_id, q.stem_text,
           q.image_asset_ids_json, q.image_filenames_json, q.image_count,
           (SELECT COUNT(*) FROM question_assets qa WHERE qa.question_id=q.question_id) AS qa_links,
           (SELECT COUNT(*) FROM image_assets ia WHERE ia.question_id=q.question_id) AS ia_direct
    FROM question_text_index q
    ORDER BY q.question_id
""")
for r in cur.fetchall():
    title = (r['stem_text'] or '')[:50]
    ids = r['image_asset_ids_json']
    names = r['image_filenames_json']
    print(f"  {r['question_id']} | count={r['image_count']} | ids_json={ids} | qa_links={r['qa_links']} | ia_direct={r['ia_direct']}")
    print(f"    title={title}")

# 4. 检查题目文本里是否引用了图片占位符但没关联
print()
print('=== STEM text containing image references (but maybe not linked) ===')
cur.execute("SELECT question_id, stem_text, image_count FROM question_text_index")
import re
img_patterns = [
    r'!\[.*?\]\(.*?\)',        # markdown image
    r'<img[^>]*>',              # html img
    r'图\s*\d',                 # 中文 "图1" "图2"
    r'如图',
    r'\[\[IMAGE[^\]]*\]\]',     # placeholder
    r'\{\{image[^}]*\}\}',      # template
    r'IMG\d{8}',
]
for r in cur.fetchall():
    stem = r['stem_text'] or ''
    full = stem
    hits = []
    for p in img_patterns:
        m = re.findall(p, full)
        if m:
            hits.append(f'{p}={len(m)}')
    has_img_ref = bool(hits)
    linked = r['image_count'] > 0
    flag = ''
    if has_img_ref and not linked:
        flag = ' <-- TEXT REFERS TO IMAGE BUT NOT LINKED'
    elif has_img_ref and linked:
        flag = ' (text+linked)'
    elif not has_img_ref and linked:
        flag = ' (linked, no text ref)'
    if hits:
        print(f"  {r['question_id']} | refs={hits} | count={r['image_count']}{flag}")

# 5. 看看 data 目录下实际有哪些图片文件
print()
print('=== Image files on disk (data/) ===')
for root, dirs, files in os.walk('data'):
    for f in files:
        if f.lower().endswith(('.png','.jpg','.jpeg','.gif','.webp','.svg')):
            full = os.path.join(root, f)
            size = os.path.getsize(full)
            print(f"  {full} ({size} bytes)")

db.close()
