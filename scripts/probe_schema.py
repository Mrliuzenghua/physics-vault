#!/usr/bin/env python3
"""列出 question_text_index 的完整 schema"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "app-db", "physics_vault.sqlite3")
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()
cur.execute("PRAGMA table_info(question_text_index)")
for r in cur.fetchall():
    print(f"{r['name']:35s} {r['type']:20s} notnull={r['notnull']} default={r['dflt_value']!r}")
db.close()
