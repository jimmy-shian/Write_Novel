# -*- coding: utf-8 -*-
import sqlite3
import json
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

ids = ["a49c3f9e-5b2e-4f5d-8258-e618f79c1a6e", "f77b3465-d23b-46e8-9e39-5f157cf2fbb9"]

for nid in ids:
    print(f"\n=================== NOVEL ID: {nid} ===================")
    novel = cursor.execute("SELECT * FROM novels WHERE id = ?", (nid,)).fetchone()
    if novel:
        print(f"Title: {novel['title']}")
        print(f"Genre: {novel['genre']}")
        print(f"Style: {novel['style']}")
    else:
        print("Novel not found in novels table!")
        
    wb = cursor.execute("SELECT * FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC LIMIT 1", (nid,)).fetchone()
    if wb:
        print(f"Worldbuilding Version: {wb['version']}")
        print(f"Worldbuilding Content Length: {len(wb['content'])}")
        print("Content Snippet (first 500 chars):")
        print(wb['content'][:500])
        print("----------------------------------------")
        # Check if JSON load works
        try:
            parsed = json.loads(wb['content'])
            print("Successfully parsed as JSON. Keys:", list(parsed.keys()))
        except Exception as e:
            print("Failed to parse as JSON directly! Error:", e)
    else:
        print("No worldbuilding record found for this novel ID!")

conn.close()
