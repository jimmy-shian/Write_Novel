# -*- coding: utf-8 -*-
import sqlite3
import sys
import os
import json

sys.path.append(os.path.abspath("."))

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

vols = cursor.execute("SELECT * FROM volumes WHERE novel_id = 'd17af413-03be-4ffe-93a9-3603f8ff9839' ORDER BY volume_index").fetchall()
print(f"Found {len(vols)} volumes")

with open("scratch/inspect_volumes_output.txt", "w", encoding="utf-8") as f:
    for v in vols:
        vd = dict(v)
        f.write(f"\n================ VOL {vd['volume_index']}: {vd['title']} ================\n")
        f.write(f"Summary: {vd['summary']}\n")
        f.write(f"Factions: {vd['factions']}\n")
        outline_str = vd['chapters_outline']
        if outline_str:
            try:
                parsed = json.loads(outline_str)
                f.write(f"Chapters count: {len(parsed)}\n")
                if parsed:
                    f.write("Sample first chapter skeleton:\n")
                    f.write(json.dumps(parsed[0], ensure_ascii=False, indent=2) + "\n")
                    f.write("Sample last chapter skeleton:\n")
                    f.write(json.dumps(parsed[-1], ensure_ascii=False, indent=2) + "\n")
            except Exception as e:
                f.write(f"JSON Parse Error: {e}\nRaw: {outline_str[:200]}\n")
        else:
            f.write("chapters_outline is NULL/empty!\n")

conn.close()
print("Inspection written to scratch/inspect_volumes_output.txt")
