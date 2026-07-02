# -*- coding: utf-8 -*-
import sqlite3
import sys
import os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('novel_factory.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# === Part 1: Structural checks ===

c.execute("SELECT * FROM sqlite_sequence")
rows = c.fetchall()
print('sqlite_sequence (tracks auto-increment max ids):')
for r in rows:
    print(f'  {dict(r) if hasattr(r, "keys") else r}')

c.execute("PRAGMA table_info(novels)")
print('\nnovels schema:')
for r in c.fetchall():
    print(f'  {r}')

c.execute("PRAGMA foreign_key_list(novels)")
fks = c.fetchall()
print(f'\nForeign keys on novels: {fks}')

c.execute("SELECT MAX(rowid), COUNT(*) FROM novels")
r = c.fetchone()
print(f'\nnovels max_rowid={r[0]}, count={r[1]}')

for t in ['chapters', 'characters', 'worldbuilding', 'chat_memory', 'volumes']:
    try:
        c.execute(f"SELECT COUNT(DISTINCT novel_id) FROM {t}")
        cnt = c.fetchone()[0]
        c.execute(f"SELECT MAX(rowid) FROM {t}")
        maxrid = c.fetchone()[0]
        print(f'{t}: distinct_novel_ids={cnt}, max_rowid={maxrid}')
    except Exception as e:
        print(f'{t}: error {e}')

for logname in ['app.log', 'server.log', 'novel_factory.log', 'access.log']:
    for root, dirs, files in os.walk('.'):
        if logname in files:
            print(f'Found log: {os.path.join(root, logname)}')

# === Part 2: Orphan detection ===

print('\n' + '=' * 60)
print('ORPHAN NOVEL DETECTION')
print('=' * 60)

c.execute("SELECT rowid, id, title, genre, created_at FROM novels")
novel_rows = c.fetchall()
current_ids = set()
for r in novel_rows:
    current_ids.add(r['id'])
    print(f"novels rowid={r['rowid']}: id={r['id']}, title={r['title']}, genre={r['genre']}, created_at={r['created_at']}")

c.execute("SELECT DISTINCT novel_id FROM chat_memory ORDER BY novel_id")
cm_novels = [r['novel_id'] for r in c.fetchall()]
print(f"\nNovel IDs in chat_memory: {cm_novels}")

c.execute("SELECT DISTINCT novel_id FROM worldbuilding ORDER BY novel_id")
wb_novels = [r['novel_id'] for r in c.fetchall()]
print(f"Novel IDs in worldbuilding: {wb_novels}")

print(f"\nCurrent novel IDs in novels table: {list(current_ids)}")

all_ids = set(cm_novels + wb_novels)
deleted_ids = all_ids - current_ids
if deleted_ids:
    print(f"\nDELETED novel IDs (exist in related tables but not in novels table): {deleted_ids}")
    for did in deleted_ids:
        c.execute("SELECT count(*) FROM chat_memory WHERE novel_id = ?", (did,))
        cm_count = c.fetchone()[0]
        c.execute("SELECT count(*) FROM worldbuilding WHERE novel_id = ?", (did,))
        wb_count = c.fetchone()[0]
        c.execute("SELECT created_at FROM chat_memory WHERE novel_id = ? ORDER BY created_at ASC LIMIT 1", (did,))
        first_cm = c.fetchone()
        c.execute("SELECT created_at FROM chat_memory WHERE novel_id = ? ORDER BY created_at DESC LIMIT 1", (did,))
        last_cm = c.fetchone()
        print(f"  {did}: {cm_count} chat_memory rows, {wb_count} worldbuilding rows")
        if first_cm:
            print(f"    First chat: {first_cm['created_at']}")
        if last_cm:
            print(f"    Last chat: {last_cm['created_at']}")
else:
    print("\nNo deleted novel IDs found in related tables (clean delete was performed)")

conn.close()
