# -*- coding: utf-8 -*-
import sqlite3
import json
import sys
import os

sys.path.append(os.path.abspath("."))

def main():
    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    novels = cursor.execute("SELECT id, title FROM novels").fetchall()
    for n in novels:
        novel_id = n['id']
        title = n['title']
        print(f"\n================ Novel ID: {novel_id} | Title: {title} ================")
        vols = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id,)).fetchall()
        for v in vols:
            vol_idx = v['volume_index']
            v_title = v['title']
            ch_count = v['chapter_count']
            
            outline_str = v['chapters_outline']
            if outline_str:
                try:
                    outline = json.loads(outline_str)
                    outline_len = len(outline)
                except Exception as e:
                    outline_len = f"Error: {e}"
            else:
                outline_len = "None"
                outline = []
                
            print(f"  Vol {vol_idx}: {v_title} | chapter_count = {ch_count} | chapters_outline length = {outline_len}")
            if isinstance(outline, list) and len(outline) > 0:
                indexes = [ch.get("chapter_index") for ch in outline if ch.get("chapter_index") is not None]
                if indexes:
                    print(f"    Chapter indexes in outline: {min(indexes)} to {max(indexes)}")
                else:
                    print(f"    No chapter indexes in outline")
            
    conn.close()

if __name__ == '__main__':
    main()
