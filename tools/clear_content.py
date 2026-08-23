# -*- coding: utf-8 -*-
"""
AI Novel Factory - 資料庫內容清理工具
支援互動式與命令列模式，安全清除特定或全部小說之生成內容（世界觀、角色、章節、大綱、對話記憶等），
並保留小說本體（novels 表）的基本元數據（標題、類型、風格等）。
"""

import os
import sys
import sqlite3
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("DB_PATH", os.path.join(PROJECT_ROOT, "data", "novel_factory.db"))

TABLES_TO_CLEAR = [
    "worldbuilding",
    "characters",
    "character_bible",
    "volumes",
    "plot_chapters",
    "chapters",
    "chat_memory",
    "director_reviews",
    "chapter_memory",
    "arc_summaries",
    "foreshadowing_blueprints",
    "foreshadowing_seeds",
    "pipeline_locks",
    "pipeline_runs",
    "pipeline_tasks",
    "chapters_backup",
    "last_agent_run",
]


def get_connection():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"資料庫檔案不存在：{DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def list_novels(conn):
    conn.row_factory = sqlite3.Row
    novels = conn.execute(
        "SELECT id, title, genre, style, pipeline_prompt, created_at FROM novels ORDER BY created_at DESC"
    ).fetchall()
    return [dict(n) for n in novels]


def show_novels(novels):
    print("\n" + "=" * 70)
    print(f"  資料庫路徑: {DB_PATH}")
    print(f"  目前共有 {len(novels)} 本小說")
    print("=" * 70)
    for i, n in enumerate(novels, 1):
        title = n.get('title') or '(無標題)'
        genre = n.get('genre') or ''
        style = n.get('style') or ''
        prompt_preview = (n.get('pipeline_prompt') or '')[:60]
        print(f"\n  [{i}] {title}")
        print(f"      ID: {n['id']}")
        if genre:
            print(f"      類型: {genre}")
        if style:
            print(f"      風格: {style}")
        if prompt_preview:
            print(f"      一鍵提示: {prompt_preview}{'...' if len(n.get('pipeline_prompt') or '') > 60 else ''}")
        print(f"      建立時間: {n.get('created_at', '—')}")
    print()


def show_novel_stats(conn, novel_id):
    conn.row_factory = sqlite3.Row
    novel = conn.execute("SELECT title FROM novels WHERE id = ?", (novel_id,)).fetchone()
    title = dict(novel)['title'] if novel else novel_id
    print(f"\n  小說「{title}」({novel_id}) 各資料表筆數：")
    for t in TABLES_TO_CLEAR:
        try:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE novel_id = ?", (novel_id,)).fetchone()[0]
            label = "筆" if cnt > 0 else "—"
            print(f"    {t:30s} {cnt:>6} {label}")
        except Exception:
            pass
    print()


def interactive_select(novels):
    while True:
        try:
            raw = input("  請輸入要清除的小說編號（多選用逗號分隔，0=全部，q=取消）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            return None

        if raw.lower() in ('q', 'quit', 'cancel', '取消'):
            print("  已取消。")
            return None

        if raw == '0':
            return [n['id'] for n in novels]

        try:
            indices = [int(x.strip()) for x in raw.split(',') if x.strip()]
            selected = []
            valid = True
            for idx in indices:
                if 1 <= idx <= len(novels):
                    selected.append(novels[idx - 1]['id'])
                else:
                    print(f"  無效編號: {idx}（範圍 1-{len(novels)}）")
                    valid = False
                    break
            if valid and selected:
                return selected
        except ValueError:
            print("  輸入格式錯誤，請用逗號分隔編號。")


def confirm_clear(conn, selected_ids):
    novels_list = list_novels(conn)
    id_to_title = {n['id']: n['title'] for n in novels_list}

    print("\n  即將清除以下小說的「所有生成內容」：")
    for nid in selected_ids:
        title = id_to_title.get(nid, nid)
        print(f"    - {title} ({nid})")

    print("\n  將保留：novels 表（標題、類型、風格、一鍵提示等基本設定）")
    print("  將重置：novels.worldview_patches（避免舊世界觀補丁污染下一輪）")
    print("  將刪除：worldbuilding, characters, character_bible, volumes,")
    print("          plot_chapters, chapters, chat_memory, director_reviews,")
    print("          chapter_memory, arc_summaries, foreshadowing_blueprints,")
    print("          foreshadowing_seeds, pipeline_locks, pipeline_runs, pipeline_tasks")

    while True:
        try:
            ans = input("\n  確認執行？此操作不可逆！(y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消。")
            return False
        if ans in ('y', 'yes', '是'):
            return True
        return False


def clear_novel(conn, novel_id):
    novel = conn.execute("SELECT title FROM novels WHERE id = ?", (novel_id,)).fetchone()
    title = dict(novel)['title'] if novel else novel_id
    print(f"\n  正在清除「{title}」的所有生成內容...")
    total = 0
    for table in TABLES_TO_CLEAR:
        try:
            cur = conn.execute(f"DELETE FROM {table} WHERE novel_id = ?", (novel_id,))
            deleted = cur.rowcount
            total += deleted
            if deleted > 0:
                print(f"    {table}: 刪除 {deleted} 筆")
        except Exception as e:
            pass

    try:
        conn.execute("UPDATE novels SET worldview_patches = '[]' WHERE id = ?", (novel_id,))
        print("    novels.worldview_patches: 重置為 []")
    except Exception as e:
        pass

    conn.commit()
    print(f"  ✅「{title}」清除完成，共刪除 {total} 筆。")
    return total


def main():
    parser = argparse.ArgumentParser(description="AI Novel Factory 資料庫內容清除工具")
    parser.add_argument("--all", action="store_true", help="直接清除所有小說的生成內容")
    parser.add_argument("--novel-id", type=str, help="指定要清除的小說 ID")
    parser.add_argument("-y", "--yes", action="store_true", help="跳過確認提示")
    args = parser.parse_args()

    conn = get_connection()
    novels = list_novels(conn)
    if not novels:
        print("  資料庫中沒有任何小說。")
        conn.close()
        return

    if args.novel_id:
        selected_ids = [args.novel_id]
    elif args.all:
        selected_ids = [n['id'] for n in novels]
    else:
        show_novels(novels)
        selected_ids = interactive_select(novels)
        if not selected_ids:
            conn.close()
            return

    for nid in selected_ids:
        show_novel_stats(conn, nid)

    if not args.yes and not confirm_clear(conn, selected_ids):
        conn.close()
        return

    grand_total = 0
    for nid in selected_ids:
        grand_total += clear_novel(conn, nid)

    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

    print(f"\n🎉 全部完成！共清除 {len(selected_ids)} 本小說，刪除 {grand_total} 筆資料。")
    print(f"📁 資料庫位置: {DB_PATH}\n")


if __name__ == "__main__":
    main()
