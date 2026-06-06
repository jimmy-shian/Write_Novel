# -*- coding: utf-8 -*-
import sqlite3
import sys
import os

sys.path.append(os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows = cursor.execute("""
        SELECT * FROM chat_memory 
        WHERE id >= 5470 AND id <= 5490 
        ORDER BY id ASC
    """).fetchall()
    
    print(f"Found {len(rows)} records:")
    for r in rows:
        print(f"\n================ ID: {r['id']} | Role: {r['role']} | Msg Type: {r['message_type']} ================")
        print(r['content'][:1500])
        
    conn.close()

if __name__ == '__main__':
    main()
