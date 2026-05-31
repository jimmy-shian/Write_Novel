import sqlite3
import json
import sys
import os

sys.path.append(os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

from db import get_volumes, get_volume_chapter_range
volumes = get_volumes("d17af413-03be-4ffe-93a9-3603f8ff9839")
print("Total volumes:", len(volumes))
for v in volumes:
    start_ch, end_ch = get_volume_chapter_range(volumes, v["volume_index"])
    print(f"Vol {v['volume_index']}: {v['title']} (chapters {start_ch} - {end_ch}, count: {v['chapter_count']})")

conn.close()
