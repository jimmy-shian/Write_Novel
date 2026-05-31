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
    print(f"Latest Novel: {novel['title']} (ID: {novel_id})")
    
    # Get latest chat memory
    chats = cursor.execute(
        "SELECT id, role, content, message_type, timestamp FROM chat_memory WHERE novel_id = ? ORDER BY id DESC LIMIT 10",
        (novel_id,)
    ).fetchall()
    
    print("--- Latest Chat Memory (Newest First) ---")
    for chat in chats:
        print(f"ID: {chat['id']} | Role: {chat['role']} | MsgType: {chat['message_type']} | Time: {chat['timestamp']}")
        content_snippet = chat['content'][:500] if chat['content'] else ""
        print(f"Content:\n{content_snippet}\n{'-'*40}")
else:
    print("No novels found!")

conn.close()
