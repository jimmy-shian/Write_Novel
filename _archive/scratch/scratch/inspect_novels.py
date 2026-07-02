# -*- coding: utf-8 -*-
import sqlite3
import json
import sys
import os
import argparse

sys.path.append(os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def show_status(conn, novel_id=None):
    cursor = conn.cursor()
    if novel_id:
        novels = cursor.execute("SELECT id, title, genre, style FROM novels WHERE id = ?", (novel_id,)).fetchall()
    else:
        novels = cursor.execute("SELECT id, title, genre, style FROM novels").fetchall()
    print(f"Total novels in database: {len(novels)}")
    for n in novels:
        nid = n['id']
        title = n['title']
        print(f"\nNovel ID: {nid} | Title: {title} | Genre: {n['genre']} | Style: {n['style']}")

        vols = cursor.execute("SELECT volume_index, title, chapter_count FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (nid,)).fetchall()
        print(f"  Volumes: {len(vols)}")
        for v in vols:
            print(f"    - Vol {v['volume_index']}: {v['title']} (Chapter Count: {v['chapter_count']})")

        chapters = cursor.execute("SELECT count(*) as c FROM chapters WHERE novel_id = ?", (nid,)).fetchone()
        print(f"  Chapters written rows count: {chapters['c']}")


def show_volumes_detail(conn, novel_id=None):
    cursor = conn.cursor()
    if novel_id:
        novels = cursor.execute("SELECT id, title FROM novels WHERE id = ?", (novel_id,)).fetchall()
    else:
        novels = cursor.execute("SELECT id, title FROM novels").fetchall()
    for n in novels:
        novel_id_val = n['id']
        title = n['title']
        print(f"\n================ Novel ID: {novel_id_val} | Title: {title} ================")
        cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index ASC", (novel_id_val,))
        vols = cursor.fetchall()
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
                    outline = []
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


def dump_volumes(conn, novel_id, output_path):
    cursor = conn.cursor()
    vols = cursor.execute("SELECT * FROM volumes WHERE novel_id = ? ORDER BY volume_index", (novel_id,)).fetchall()
    print(f"Found {len(vols)} volumes")

    with open(output_path, "w", encoding="utf-8") as f:
        for v in vols:
            vd = dict(v)
            f.write(f"\n================ VOL {vd['volume_index']}: {vd['title']} ================\n")
            f.write(f"Summary: {vd.get('summary', '')}\n")
            f.write(f"Factions: {vd.get('factions', '')}\n")
            outline_str = vd.get('chapters_outline')
            if outline_str:
                try:
                    parsed = json.loads(outline_str)
                    f.write(f"Chapters count: {len(parsed)}\n")
                    if parsed:
                        f.write("Sample first chapter skeleton:\n")
                        f.write(json.dumps(parsed[0], ensure_ascii=False, indent=2) + "\n")
                        f.write("Sample last chapter skeleton:\n")
                        f.write(json.dumps(parsed[-1], ensure_ascii=False, indent=2) + "\n")
                except Exception as e:
                    f.write(f"JSON Parse Error: {e}\nRaw: {outline_str[:200]}\n")
            else:
                f.write("chapters_outline is NULL/empty!\n")

    print(f"Inspection written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Inspect novels, volumes, and chapter outlines")
    parser.add_argument("--novel", "-n", help="Filter by novel_id (defaults to all novels)")
    parser.add_argument("--detail", "-d", action="store_true", help="Show chapters_outline details per volume")
    parser.add_argument("--output", "-o", type=str, help="Dump full volume details to a file (requires --novel)")
    args = parser.parse_args()

    conn = sqlite3.connect("novel_factory.db")
    conn.row_factory = sqlite3.Row

    if args.output:
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
        dump_volumes(conn, novel_id, args.output)
    elif args.detail:
        show_volumes_detail(conn, novel_id=args.novel)
    else:
        show_status(conn, novel_id=args.novel)

    conn.close()


if __name__ == '__main__':
    main()
