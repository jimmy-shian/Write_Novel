# -*- coding: utf-8 -*-
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"C:\Users\user\Desktop\test_html\patches\gateway.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT count(*) FROM models_config")
count = cursor.fetchone()[0]
print(f"Row count in models_config: {count}")

cursor.execute("SELECT * FROM models_config")
rows = cursor.fetchall()
for r in rows:
    print(r)

conn.close()
