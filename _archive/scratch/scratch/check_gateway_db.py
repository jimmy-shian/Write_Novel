# -*- coding: utf-8 -*-
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"C:\Users\user\Desktop\test_html\patches\gateway.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for table in ["api_keys", "available_models"]:
    print(f"=== SCHEMA FOR {table} ===")
    cursor.execute(f"PRAGMA table_info({table})")
    for col in cursor.fetchall():
        print(col)
    
    print(f"=== ROWS FOR {table} ===")
    cursor.execute(f"SELECT * FROM {table}")
    for row in cursor.fetchall():
        print(row)
    print("-" * 50)

conn.close()
