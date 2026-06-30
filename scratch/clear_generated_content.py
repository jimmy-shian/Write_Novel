# -*- coding: utf-8 -*-
import sqlite3
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "novel_factory.db"

TABLES_TO_CLEAR = [
    "worldbuilding",
    "characters",
    "volumes",
    "plot_chapters",
    "chapters",
    "chat_memory",
    "foreshadowing_blueprints",
    "pipeline_locks",
    "chapters_backup",
    "last_agent_run",
]


def list_novels(conn):
    conn.row_factory = sqlite3.Row
    novels = conn.execute("SELECT id, title, genre, style, pipeline_prompt, created_at FROM novels ORDER BY created_at DESC").fetchall()
    return [dict(n) for n in novels]


def show_novels(novels):
    print("\n" + "=" * 70)
    print(f"  資料庫中共有 {len(novels)} 本小說")
    print("=" * 70)
    for i, n in enumerate(novels, 1):
        title = n['title'] or '(無標題)'
        genre = n['genre'] or ''
        style = n['style'] or ''
        prompt_preview = (n.get('pipeline_prompt') or '')[:60]
        print(f"\n  [{i}] {title}")
        print(f"      ID: {n['id']}")
        if genre:
            print(f"      類型: {genre}")
        if style:
            print(f"      風格: {style}")
        if prompt_preview:
            print(f"      一鍵提示: {prompt_preview}{'...' if len(n.get('pipeline_prompt') or '') > 60 else ''}")
        print(f"      建立時間: {n['created_at']}")
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
            raw = input("  請輸入要清除的小說編號（多选用逗號分隔，0=全部，q=取消）: ").strip()
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

    print("\n  將保留：novels 表（標題、類型、風格、一鍵提示等設定）")
    print("  將刪除：worldbuilding, characters, volumes, plot_chapters,")
    print("          chapters, chat_memory, foreshadowing_blueprints,")
    print("          pipeline_locks, chapters_backup, last_agent_run")

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
            print(f"    {table}: 刪除 {deleted} 筆")
        except Exception as e:
            print(f"    {table}: 跳過 ({e})")
    conn.commit()
    print(f"  「{title}」清除完成，共刪除 {total} 筆。")
    return total


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")

    novels = list_novels(conn)
    if not novels:
        print("  資料庫中沒有任何小說。")
        conn.close()
        return

    show_novels(novels)

    selected_ids = interactive_select(novels)
    if not selected_ids:
        conn.close()
        return

    for nid in selected_ids:
        show_novel_stats(conn, nid)

    if not confirm_clear(conn, selected_ids):
        conn.close()
        return

    grand_total = 0
    for nid in selected_ids:
        grand_total += clear_novel(conn, nid)

    conn.execute("PRAGMA foreign_keys = ON")
    conn.close()

    print(f"\n  全部完成！共清除 {len(selected_ids)} 本小說，刪除 {grand_total} 筆資料。")
    print("  已保留：novels 表（小說基本設定）\n")


if __name__ == "__main__":
    main()