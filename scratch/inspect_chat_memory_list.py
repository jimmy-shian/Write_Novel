import sqlite3
import sys
import os

sys.path.append(os.path.abspath("."))
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("novel_factory.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

chats = cursor.execute(
    "SELECT id, role, content, message_type, timestamp FROM chat_memory ORDER BY id DESC LIMIT 15"
).fetchall()

for chat in reversed(chats):
    print(f"ID: {chat['id']} | Role: {chat['role']} | MsgType: {chat['message_type']} | Time: {chat['timestamp']}")
    print(chat['content'][:600])
    print("-" * 60)

conn.close()
