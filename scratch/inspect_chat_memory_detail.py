import sqlite3
import sys
import os

sys.path.append(os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get latest novel
novel = cursor.execute("SELECT * FROM novels ORDER BY id DESC LIMIT 1").fetchone()
if novel:
    novel_id = novel["id"]
    chat = cursor.execute(
        "SELECT id, role, content, message_type, timestamp FROM chat_memory WHERE id = 1054"
    ).fetchone()
    if chat:
        print(f"ID: {chat['id']} | Role: {chat['role']} | MsgType: {chat['message_type']} | Time: {chat['timestamp']}")
        print("Content:")
        print(chat['content'])
        print("-" * 80)
    else:
        print("Chat not found")
else:
    print("No novels found!")

conn.close()
