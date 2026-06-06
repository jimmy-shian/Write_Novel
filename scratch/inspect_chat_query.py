# -*- coding: utf-8 -*-
import sqlite3
import sys
import os

sys.path.append(os.path.abspath("."))

def main():
    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows = cursor.execute("SELECT * FROM chat_memory WHERE content LIKE '%151.67%'").fetchall()
    print(f"Found {len(rows)} matching chat memory records:")
    for r in rows:
        print(f"\nID: {r['id']} | Role: {r['role']} | Msg Type: {r['message_type']}")
        print(f"Content: {r['content']}")
        
    conn.close()

if __name__ == '__main__':
    main()
