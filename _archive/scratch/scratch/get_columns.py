# -*- coding: utf-8 -*-
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = "novel_factory.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(last_agent_run)")
cols = cursor.fetchall()
for col in cols:
    print(col)
conn.close()
