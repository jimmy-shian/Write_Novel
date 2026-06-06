# -*- coding: utf-8 -*-
import sqlite3
import sys
import os
import json

sys.path.append(os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # List all novels
    novels = cursor.execute("SELECT id, title, genre, style FROM novels").fetchall()
    print(f"Total novels in database: {len(novels)}")
    for n in novels:
        nid = n['id']
        title = n['title']
        print(f"\nNovel ID: {nid} | Title: {title} | Genre: {n['genre']} | Style: {n['style']}")
        
        # Volumes count
        vols = cursor.execute("SELECT volume_index, title, chapter_count FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (nid,)).fetchall()
        print(f"  Volumes: {len(vols)}")
        for v in vols:
            print(f"    - Vol {v['volume_index']}: {v['title']} (Chapter Count: {v['chapter_count']})")
            
        # Chapters count
        chapters = cursor.execute("SELECT count(*) as c FROM chapters WHERE novel_id = ?", (nid,)).fetchone()
        print(f"  Chapters written rows count: {chapters['c']}")
        
    conn.close()

if __name__ == '__main__':
    main()
