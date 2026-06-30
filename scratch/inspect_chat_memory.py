# -*- coding: utf-8 -*-
import sqlite3
import sys
import os
import argparse

sys.path.append(os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def list_recent(conn, novel_id=None, limit=10, truncate=600):
    cursor = conn.cursor()
    if novel_id:
        cursor.execute(
            "SELECT id, novel_id, role, content, message_type, timestamp FROM chat_memory WHERE novel_id = ? ORDER BY id DESC LIMIT ?",
            (novel_id, limit)
        )
    else:
        cursor.execute(
            "SELECT id, novel_id, role, content, message_type, timestamp FROM chat_memory ORDER BY id DESC LIMIT ?",
            (limit,)
        )

    chats = cursor.fetchall()
    print(f"--- Latest {len(chats)} Chat Memory Records {'(novel: ' + str(novel_id) + ')' if novel_id else '(all novels)'} ---")
    for chat in reversed(chats):
        row = dict(chat) if hasattr(chat, 'keys') else dict(zip([d[0] for d in cursor.description], chat))
        print(f"ID: {row['id']} | Novel: {row.get('novel_id', '?')[:8]}... | Role: {row['role']} | MsgType: {row.get('message_type', '')} | Time: {row.get('timestamp', '')}")
        content = row.get('content', '') or ''
        print(content[:truncate])
        print("-" * 60)


def list_by_id_range(conn, start_id, end_id, truncate=1500):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM chat_memory WHERE id >= ? AND id <= ? ORDER BY id ASC",
        (start_id, end_id)
    )
    rows = cursor.fetchall()
    print(f"Found {len(rows)} records in range {start_id}-{end_id}:")
    for r in rows:
        row = dict(r) if hasattr(r, 'keys') else dict(zip([d[0] for d in cursor.description], r))
        print(f"\n================ ID: {row['id']} | Role: {row['role']} | Msg Type: {row.get('message_type', '')} ================")
        print((row.get('content', '') or '')[:truncate])


def list_by_id(conn, record_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, message_type, timestamp FROM chat_memory WHERE id = ?",
        (record_id,)
    )
    chat = cursor.fetchone()
    if chat:
        row = dict(chat) if hasattr(chat, 'keys') else dict(zip([d[0] for d in cursor.description], chat))
        print(f"ID: {row['id']} | Role: {row['role']} | MsgType: {row.get('message_type', '')} | Time: {row.get('timestamp', '')}")
        print("Content:")
        print(row.get('content', ''))
        print("-" * 80)
    else:
        print(f"Chat record id={record_id} not found")


def search_content(conn, search_term):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM chat_memory WHERE content LIKE ?",
        (f'%{search_term}%',)
    )
    rows = cursor.fetchall()
    print(f"Found {len(rows)} matching chat memory records for '{search_term}':")
    for r in rows:
        row = dict(r) if hasattr(r, 'keys') else dict(zip([d[0] for d in cursor.description], r))
        print(f"\nID: {row['id']} | Role: {row['role']} | Msg Type: {row.get('message_type', '')}")
        print(f"Content: {row.get('content', '')}")


def main():
    parser = argparse.ArgumentParser(description="Inspect chat_memory records")
    parser.add_argument("--novel", "-n", help="Filter by novel_id (defaults to latest novel)")
    parser.add_argument("--all-novels", action="store_true", help="List across all novels (no novel filter)")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of records to show (default: 10)")
    parser.add_argument("--id", type=int, help="Show a single record by ID (full content)")
    parser.add_argument("--range", type=str, help="Show records by ID range (e.g. 5470-5490)")
    parser.add_argument("--search", "-s", type=str, help="Search content for a keyword/phrase")
    args = parser.parse_args()

    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row

    if args.id:
        list_by_id(conn, args.id)
    elif args.range:
        parts = args.range.split('-')
        if len(parts) != 2:
            print("Invalid range format. Use start-end (e.g. 5470-5490)")
            conn.close()
            return
        start_id, end_id = int(parts[0]), int(parts[1])
        list_by_id_range(conn, start_id, end_id)
    elif args.search:
        search_content(conn, args.search)
    elif args.all_novels:
        list_recent(conn, novel_id=None, limit=args.limit)
    else:
        novel_id = args.novel
        if not novel_id:
            cursor = conn.cursor()
            novel = cursor.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
            if novel:
                novel_id = novel["id"]
                print(f"Auto-detected latest novel: {novel_id}")
            else:
                print("No novels found in database!")
                conn.close()
                return
        list_recent(conn, novel_id=novel_id, limit=args.limit)

    conn.close()


if __name__ == '__main__':
    main()
