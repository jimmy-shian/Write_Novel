import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
cursor = conn.cursor()
count = cursor.execute("SELECT COUNT(*) FROM chat_memory").fetchone()[0]
print(f"Total rows in chat_memory: {count}")
rows = cursor.execute("SELECT * FROM chat_memory").fetchall()
for r in rows:
    row_dict = dict(zip([d[0] for d in cursor.description], r))
    # Remove large content to avoid massive prints, but print keys and snippet
    content = row_dict.get("content", "")
    row_dict["content"] = content[:500] + "..." if len(content) > 500 else content
    print(row_dict)
conn.close()
