import sqlite3
import json

DB_PATH = 'novel_factory.db'
NOVEL_ID = 'baa16cae-c879-412c-9c8a-78a048df9a5e'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Get novel
novel = cursor.execute("SELECT * FROM novels WHERE id = ?", (NOVEL_ID,)).fetchone()
if novel:
    print(f"Novel Title: {novel['title']}")
else:
    print("Novel not found")
    
# 2. Get volumes
vols = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (NOVEL_ID,)).fetchall()
print(f"Volumes count: {len(vols)}")
for v in vols:
    print(f"  Vol {v['volume_index']}: {v['title']} | is_dirty: {v['is_dirty']}")
    outline = v['chapters_outline']
    if outline:
        try:
            ch_list = json.loads(outline)
            print(f"    Chapters count: {len(ch_list)}")
            if ch_list:
                print(f"    Chapters: {ch_list[0].get('chapter_index')} to {ch_list[-1].get('chapter_index')}")
        except:
            print("    Error parsing chapters outline")
    else:
        print("    No chapters outline")

# 3. Get chapters (written)
chaps = cursor.execute("SELECT * FROM chapters WHERE novel_id = ? GROUP BY chapter_index ORDER BY chapter_index ASC", (NOVEL_ID,)).fetchall()
print(f"Written chapters count: {len(chaps)}")
for c in chaps:
    print(f"  Chapter {c['chapter_index']}: len={len(c['content']) if c['content'] else 0} | is_dirty: {c['is_dirty']} | synopsis: {c['synopsis']}")

conn.close()


