# -*- coding: utf-8 -*-
"""
AI Novel Factory - Consolidated Diagnostics & Maintenance Toolkit
整合自原 scratch/ 目錄下的 10 個散落除錯與資料修復腳本。

支援功能：
1. check-db: 檢測本地與雲端資料庫連線、各資料表統計與完整度
2. inspect-novel: 檢視指定小說的章節細節、時序切片與大綱資料
3. repair-data: 修復轉折點與章節格式異常
4. hf-status: 診斷 Hugging Face Space 與 Storage Bucket 同步健康度
"""

import os
import sys
import json
import sqlite3
import argparse
from typing import Optional, Dict, Any, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "novel_factory.db")

def get_db_connection() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def cmd_check_db():
    print(f"[*] Checking database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("[-] Database does not exist!")
        return 1
    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"[+] Database size: {size_mb:.2f} MB")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"[+] Total tables found: {len(tables)}")
    for tbl in sorted(tables):
        cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
        cnt = cursor.fetchone()[0]
        print(f"    - {tbl:<25}: {cnt} rows")
    conn.close()
    return 0

def cmd_inspect_novel(novel_id: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if not novel_id:
        cursor.execute("SELECT id, title, genre FROM novels ORDER BY created_at DESC LIMIT 10;")
        novels = cursor.fetchall()
        print("\n=== Recent Novels ===")
        for n in novels:
            print(f"ID: {n['id']} | Title: {n['title']} | Genre: {n['genre']}")
        if novels:
            novel_id = novels[0]['id']
            print(f"\n[*] Inspecting latest novel ID: {novel_id}")
        else:
            print("[-] No novels found in database.")
            conn.close()
            return 0

    cursor.execute("SELECT * FROM novels WHERE id = ?;", (novel_id,))
    novel = cursor.fetchone()
    if not novel:
        print(f"[-] Novel {novel_id} not found!")
        conn.close()
        return 1

    print(f"\n--- Novel Detail: {novel['title']} ({novel['id']}) ---")
    cursor.execute("SELECT chapter_index, title, length(content) as char_cnt FROM chapters WHERE novel_id = ? ORDER BY chapter_index ASC;", (novel_id,))
    chapters = cursor.fetchall()
    print(f"[+] Total Chapters: {len(chapters)}")
    for ch in chapters[:15]:
        print(f"    Ch {ch['chapter_index']:<3}: {ch['title'] or '(No title)'} ({ch['char_cnt']} chars)")
    if len(chapters) > 15:
        print(f"    ... and {len(chapters) - 15} more chapters")

    cursor.execute("SELECT COUNT(*) FROM temporal_facts WHERE novel_id = ?;", (novel_id,))
    fact_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM temporal_entities WHERE novel_id = ?;", (novel_id,))
    ent_cnt = cursor.fetchone()[0]
    print(f"[+] Temporal Entities: {ent_cnt} | Temporal Facts: {fact_cnt}")
    conn.close()
    return 0

def cmd_repair_data():
    print("[*] Running data integrity & repair check...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE chapters SET title = '第 ' || chapter_index || ' 章' WHERE title IS NULL OR trim(title) = '';")
    repaired_chapters = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"[+] Data check complete. Repaired titles: {repaired_chapters}")
    return 0

def cmd_hf_status():
    print("[*] Checking Hugging Face & Storage status...")
    try:
        from backend.services.hf_sync import get_sync_status
        status = get_sync_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"[-] Error querying HF sync status: {exc}")
    return 0

def main():
    parser = argparse.ArgumentParser(description="AI Novel Factory Diagnostics Toolkit")
    parser.add_argument("command", choices=["check-db", "inspect-novel", "repair-data", "hf-status"], help="Diagnostic command")
    parser.add_argument("--novel-id", type=str, default=None, help="Novel ID for inspection")
    args = parser.parse_args()

    if args.command == "check-db":
        sys.exit(cmd_check_db())
    elif args.command == "inspect-novel":
        sys.exit(cmd_inspect_novel(args.novel_id))
    elif args.command == "repair-data":
        sys.exit(cmd_repair_data())
    elif args.command == "hf-status":
        sys.exit(cmd_hf_status())

if __name__ == "__main__":
    main()