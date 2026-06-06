# -*- coding: utf-8 -*-
import sqlite3
import sys
import os

sys.path.append(os.path.abspath("."))

def main():
    novel_id = '8e86fdc7-0c26-468d-9781-3f75a1e9fec4'
    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows = cursor.execute("""
        SELECT chapter_index, count(*) as count, max(version) as max_version
        FROM chapters
        WHERE novel_id = ?
        GROUP BY chapter_index
        ORDER BY chapter_index ASC
    """, (novel_id,)).fetchall()
    
    print(f"Total distinct chapter indices in 'chapters' table: {len(rows)}")
    if rows:
        print(f"Index range: {rows[0]['chapter_index']} to {rows[-1]['chapter_index']}")
        
        # Check indices above 240
        above_240 = [dict(r) for r in rows if r['chapter_index'] > 240]
        print(f"Indices > 240: count = {len(above_240)}")
        if above_240:
            print(f"Sample indices > 240: {[r['chapter_index'] for r in above_240[:20]]}...")
            
    conn.close()

if __name__ == '__main__':
    main()
