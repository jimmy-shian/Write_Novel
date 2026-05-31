import sqlite3
import sys
import os

sys.path.append(os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

wb = cursor.execute("SELECT * FROM worldbuilding ORDER BY version DESC LIMIT 1").fetchone()
if wb:
    wbd = dict(wb)
    print("--- Latest Worldbuilding Content ---")
    print(wbd["content"][:1000])
    with open("scratch/worldbuilding_raw.txt", "w", encoding="utf-8") as f:
        f.write(wbd["content"])
else:
    print("No worldbuilding found!")

conn.close()
