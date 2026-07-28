import sqlite3, json

db = sqlite3.connect('data/app-db/physics_vault.sqlite3')
db.row_factory = sqlite3.Row

print('=== question_assets schema ===')
cols = db.execute('PRAGMA table_info(question_assets)').fetchall()
for c in cols:
    print(c['name'], c['type'])

print('\n=== question_assets data ===')
rows = db.execute('SELECT * FROM question_assets LIMIT 10').fetchall()
for r in rows:
    print(dict(r))

print('\n=== image_assets schema ===')
cols2 = db.execute('PRAGMA table_info(image_assets)').fetchall()
for c in cols2:
    print(c['name'], c['type'])

print('\n=== image_assets data ===')
rows2 = db.execute('SELECT * FROM image_assets LIMIT 10').fetchall()
for r in rows2:
    print(dict(r))

print('\n=== question_text_index schema ===')
cols3 = db.execute('PRAGMA table_info(question_text_index)').fetchall()
for c in cols3:
    print(c['name'], c['type'])

print('\n=== question_text_index (image fields) ===')
rows3 = db.execute('SELECT question_id, image_filenames FROM question_text_index LIMIT 10').fetchall()
for r in rows3:
    print(r['question_id'], '->', r['image_filenames'])
