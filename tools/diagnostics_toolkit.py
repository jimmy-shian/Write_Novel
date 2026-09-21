# -*- coding: utf-8 -*-
"""
AI Novel Factory - Consolidated Diagnostics & Maintenance Toolkit
整合自原 scratch/ 目錄下的 10 個散落除錯與資料修復腳本。
已對齊現行專案邏輯：
- DB 路徑解析與 backend.persistence.connection 一致（支援 DB_PATH 環境變數 / .env）
- chapters 表已無 title 欄位，改以 synopsis 呈現與修復
- 涵蓋 Story Engine 2.0（setting_systems / conflict_signatures / narrative_audits）
  與時序記憶圖譜（temporal_*）等新式資料表

支援功能：
1. check-db: 檢測資料庫連線、各資料表統計與完整度
2. inspect-novel: 檢視指定小說的章節、卷冊、大綱與敘事引擎資料
3. repair-data: 修復章節 synopsis 空值等格式異常
4. hf-status: 診斷 Hugging Face Space 與 Storage Bucket 同步健康度
"""

import os
import sys
import json
import sqlite3
import argparse
from typing import Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- DB 路徑解析：優先沿用 backend.persistence.connection 的官方邏輯 ---
try:
    sys.path.insert(0, PROJECT_ROOT)
    from backend.persistence.connection import DB_PATH  # noqa: E402
except Exception:
    # Fallback：與 connection.py 相同的環境變數 / 預設路徑規則
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)
    DB_PATH = os.path.abspath(
        os.getenv("DB_PATH", os.path.join(PROJECT_ROOT, "data", "novel_factory.db"))
    )


def get_db_connection() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # 對齊 backend.persistence.connection._configure_sqlite_connection 的唯讀安全 PRAGMA
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?;", (table,)
    )
    return cursor.fetchone() is not None


def _safe_count(cursor, table: str, where: str = "", params: tuple = ()) -> Optional[int]:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table} {where};", params)
        return cursor.fetchone()[0]
    except sqlite3.Error:
        return None


def cmd_check_db():
    print(f"[*] Checking database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("[-] Database does not exist!")
        return 1

    size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    print(f"[+] Database size: {size_mb:.2f} MB")
    # WAL 模式下附屬檔案也計入參考
    for suffix in ("-wal", "-shm"):
        side = DB_PATH + suffix
        if os.path.exists(side):
            print(f"    - {suffix} file: {os.path.getsize(side) / (1024 * 1024):.2f} MB")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        print(f"[+] Integrity check: {result}")
    except sqlite3.Error as exc:
        print(f"[-] Integrity check failed: {exc}")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"[+] Total tables found: {len(tables)}")
    for tbl in sorted(tables):
        cnt = _safe_count(cursor, tbl)
        cnt_str = f"{cnt} rows" if cnt is not None else "(error)"
        print(f"    - {tbl:<28}: {cnt_str}")
    conn.close()
    return 0


def cmd_inspect_novel(novel_id: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    if not _table_exists(cursor, "novels"):
        print("[-] 'novels' table not found. Run the app once to initialize the DB.")
        conn.close()
        return 1

    if not novel_id:
        cursor.execute(
            "SELECT id, title, genre, created_at FROM novels ORDER BY created_at DESC LIMIT 10;"
        )
        novels = cursor.fetchall()
        print("\n=== Recent Novels ===")
        for n in novels:
            print(f"ID: {n['id']} | Title: {n['title']} | Genre: {n['genre'] or '—'} | Created: {n['created_at']}")
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

    # 章節（chapters 現行 schema 無 title，改用 synopsis 摘要）
    cursor.execute(
        """SELECT chapter_index, synopsis, length(content) as char_cnt,
                  version, is_dirty
           FROM chapters WHERE novel_id = ? ORDER BY chapter_index ASC;""",
        (novel_id,),
    )
    chapters = cursor.fetchall()
    print(f"[+] Total Chapters: {len(chapters)}")
    for ch in chapters[:15]:
        synopsis = (ch['synopsis'] or '').strip().replace('\n', ' ')[:40] or '(No synopsis)'
        dirty = ' [dirty]' if ch['is_dirty'] else ''
        print(f"    Ch {ch['chapter_index']:<3}: {synopsis} ({ch['char_cnt'] or 0} chars, v{ch['version']}){dirty}")
    if len(chapters) > 15:
        print(f"    ... and {len(chapters) - 15} more chapters")

    # 卷冊
    if _table_exists(cursor, "volumes"):
        cursor.execute(
            "SELECT volume_index, title, chapter_count FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC;",
            (novel_id,),
        )
        volumes = cursor.fetchall()
        print(f"[+] Volumes: {len(volumes)}")
        for v in volumes:
            print(f"    Vol {v['volume_index']}: {v['title']} (planned {v['chapter_count']} chapters)")

    # 敘事記憶 / 時序圖譜 / Story Engine 2.0 統計
    stats = [
        ("Temporal Entities", "temporal_entities"),
        ("Temporal Facts", "temporal_facts"),
        ("Temporal Episodes", "temporal_episodes"),
        ("Chapter Memory", "chapter_memory"),
        ("Arc Summaries", "arc_summaries"),
        ("Foreshadowing Seeds", "foreshadowing_seeds"),
        ("Setting Systems", "setting_systems"),
        ("Conflict Signatures", "conflict_signatures"),
        ("Narrative Audits (unresolved)", "narrative_audits", " AND resolved = 0"),
        ("Director Reviews", "director_reviews"),
        ("Pipeline Runs", "pipeline_runs"),
    ]
    print("[+] Narrative Engine Stats:")
    for item in stats:
        label, table = item[0], item[1]
        extra = item[2] if len(item) > 2 else ""
        if not _table_exists(cursor, table):
            continue
        where = f"WHERE novel_id = ?{extra}"
        cnt = _safe_count(cursor, table, where, (novel_id,))
        if cnt is None:
            continue
        print(f"    - {label:<30}: {cnt}")

    conn.close()
    return 0


def cmd_repair_data():
    print("[*] Running data integrity & repair check...")
    conn = get_db_connection()
    cursor = conn.cursor()

    if not _table_exists(cursor, "chapters"):
        print("[-] 'chapters' table not found.")
        conn.close()
        return 1

    # 現行 chapters schema 無 title 欄位；修復目標改為空的 synopsis
    # （以章節內容前 80 字作為摘要填入）
    cursor.execute("""
        UPDATE chapters
        SET synopsis = trim(substr(content, 1, 80))
        WHERE (synopsis IS NULL OR trim(synopsis) = '')
          AND content IS NOT NULL AND trim(content) != '';
    """)
    repaired_synopsis = cursor.rowcount
    conn.commit()

    # 報告 dirty 章節數量（供人工判斷是否需要重新生成）
    dirty_cnt = _safe_count(cursor, "chapters", "WHERE is_dirty = 1") or 0
    orphan_cnt = 0
    if _table_exists(cursor, "novels"):
        cursor.execute(
            "SELECT COUNT(*) FROM chapters WHERE novel_id NOT IN (SELECT id FROM novels);"
        )
        orphan_cnt = cursor.fetchone()[0]

    conn.close()
    print(f"[+] Data check complete. Repaired empty synopses: {repaired_synopsis}")
    print(f"[+] Chapters flagged dirty: {dirty_cnt}")
    print(f"[+] Orphan chapters (novel missing): {orphan_cnt}")
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
    parser.add_argument(
        "command",
        choices=["check-db", "inspect-novel", "repair-data", "hf-status"],
        help="Diagnostic command",
    )
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