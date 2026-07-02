# -*- coding: utf-8 -*-
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

db_path = "novel_factory.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n=== RECENT LAST AGENT RUN ===")
try:
    cursor.execute("SELECT novel_id, agent_name, input_data, output_data, timestamp FROM last_agent_run ORDER BY timestamp DESC LIMIT 3")
    rows = cursor.fetchall()
    for row in rows:
        print(f"Agent: {row[1]} | Time: {row[4]}")
        print(f"Input: {row[2][:300]}...")
        print(f"Output: {row[3][:300]}...")
        print("Length of output:", len(row[3]))
        print("-" * 50)
except Exception as e:
    print("Error reading last_agent_run:", e)

conn.close()
