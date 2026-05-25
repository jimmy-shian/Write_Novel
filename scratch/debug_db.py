import sqlite3
import json

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

with open("scratch/db_log.txt", "w", encoding="utf-8") as f:
    f.write("=== NOVELS ===\n")
    novels = cursor.execute("SELECT * FROM novels").fetchall()
    for n in novels:
        f.write(str(dict(n)) + "\n")

    f.write("\n=== VOLUMES ===\n")
    volumes = cursor.execute("SELECT * FROM volumes").fetchall()
    for v in volumes:
        f.write(str(dict(v)) + "\n")

    f.write("\n=== WORLD_BUILDING ===\n")
    wb = cursor.execute("SELECT * FROM worldbuilding").fetchall()
    for w in wb:
        w_d = dict(w)
        w_d["content"] = w_d["content"][:200] + "..." if w_d["content"] else ""
        f.write(str(w_d) + "\n")

    f.write("\n=== PLOT_CHAPTERS ===\n")
    plots = cursor.execute("SELECT * FROM plot_chapters").fetchall()
    for p in plots:
        p_d = dict(p)
        p_d["outline_json"] = p_d["outline_json"][:200] + "..." if p_d["outline_json"] else ""
        f.write(str(p_d) + "\n")

    f.write("\n=== CHAPTERS ===\n")
    chapters = cursor.execute("SELECT * FROM chapters").fetchall()
    for c in chapters:
        c_d = dict(c)
        c_d["content"] = c_d["content"][:200] + "..." if c_d["content"] else ""
        f.write(str(c_d) + "\n")

conn.close()
print("Successfully wrote db log to scratch/db_log.txt")


