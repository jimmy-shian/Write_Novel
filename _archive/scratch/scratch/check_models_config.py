# -*- coding: utf-8 -*-
import sqlite3
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"C:\Users\user\Desktop\test_html\patches\gateway.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== models_config ===")
try:
    cursor.execute("SELECT * FROM models_config")
    for row in cursor.fetchall():
        print(row)
except Exception as e:
    print("Error:", e)

conn.close()
