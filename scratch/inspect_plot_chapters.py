import sqlite3
import sys
import os
import json

sys.path.append(os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get latest novel
novel = cursor.execute("SELECT * FROM novels ORDER BY id DESC LIMIT 1").fetchone()
if novel:
    novel_id = novel["id"]
    row = cursor.execute(
        "SELECT * FROM plot_chapters WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    
    if row:
        print(f"Version: {row['version']}")
        try:
            parsed = json.loads(row["outline_json"])
            ch_list = parsed.get("chapters", [])
            print(f"Total chapters in latest plot_chapters: {len(ch_list)}")
            detailed = []
            for ch in ch_list:
                evs = ch.get("events") or ch.get("scenes")
                if evs and isinstance(evs, list) and len(evs) > 0:
                    detailed.append(ch.get("chapter_index"))
            print(f"Detailed chapters (with events/scenes): {detailed}")
        except Exception as e:
            print("Error parsing JSON:", e)
    else:
        print("No plot_chapters entries!")
else:
    print("No novels found!")

conn.close()
