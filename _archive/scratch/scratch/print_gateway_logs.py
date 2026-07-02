# -*- coding: utf-8 -*-
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = r"C:\Users\user\Desktop\test_html\patches\gateway.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Tables in gateway.db:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in cursor.fetchall():
    print("-", row[0])

print("\n=== RECENT GATEWAY LOGS ===")
try:
    cursor.execute("SELECT id, level, message, timestamp FROM logs ORDER BY id DESC LIMIT 20")
    for row in cursor.fetchall():
        print(f"[{row[3]}] [{row[1].upper()}] {row[2]}")
except Exception as e:
    print("Error reading logs table:", e)

conn.close()
