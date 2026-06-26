import sqlite3

conn = sqlite3.connect('novel_factory.db')
tables = ['characters', 'volumes', 'chapters', 'chat_memory', 'plot_chapters', 'worldbuilding', 'foreshadowing_blueprints']
print('DB row counts after clearing:')
for t in tables:
    cnt = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    print(f' - {t}: {cnt}')
conn.close()