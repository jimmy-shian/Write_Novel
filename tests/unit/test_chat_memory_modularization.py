# -*- coding: utf-8 -*-
import pytest
import uuid
from backend.persistence.connection import get_db_connection
from backend.persistence.repositories.chat_memory import (
    save_chat_message,
    get_chat_memory,
    clear_chat_memory,
)
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_chat_memory_crud_and_query_all():
    novel_id = f"test_novel_{uuid.uuid4().hex[:8]}"
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO novels (id, title, genre, style) VALUES (?, ?, ?, ?)",
        (novel_id, "Chat Test Novel", "Fantasy", "Standard"),
    )
    conn.commit()

    try:
        # Save messages of different types
        save_chat_message(novel_id, "director", "【總監通報】結構完整", thinking="思考細節1", message_type="chat")
        save_chat_message(novel_id, "assistant", "第 1 章骨架建立完畢", thinking=None, message_type="pipeline")
        save_chat_message(novel_id, "user", "請加強主角動機", thinking=None, message_type="chat")

        # Query all (message_type=None or 'all')
        all_records = get_chat_memory(novel_id, limit=50, message_type=None)
        assert len(all_records) == 3
        # Ensure 'pipeline' message was not filtered out
        types = [r["message_type"] for r in all_records]
        assert "pipeline" in types
        assert "chat" in types

        # Check thinking is preserved
        director_msg = next(r for r in all_records if r["role"] == "director")
        assert director_msg["thinking"] == "思考細節1"
        assert director_msg["content"] == "【總監通報】結構完整"

        # Query specific filter
        pipeline_only = get_chat_memory(novel_id, limit=50, message_type="pipeline")
        assert len(pipeline_only) == 1
        assert pipeline_only[0]["role"] == "assistant"

        # Test API endpoint GET /api/novels/{novel_id}/chat-memory
        res = client.get(f"/api/novels/{novel_id}/chat-memory?limit=50")
        assert res.status_code == 200
        data = res.json()
        assert "chat_memory" in data
        assert len(data["chat_memory"]) == 3

        # Test single message deletion via API
        first_msg_id = data["chat_memory"][0]["id"]
        del_res = client.delete(f"/api/novels/{novel_id}/chat-memory/{first_msg_id}")
        assert del_res.status_code == 200
        after_del = get_chat_memory(novel_id)
        assert len(after_del) == 2
        assert not any(m["id"] == first_msg_id for m in after_del)

        # Test clear_chat_memory by message_type
        clear_chat_memory(novel_id, message_type="pipeline")
        after_type_clear = get_chat_memory(novel_id)
        assert not any(m["message_type"] == "pipeline" for m in after_type_clear)

        # Test clear_chat_memory all
        clear_chat_memory(novel_id)
        cleared_records = get_chat_memory(novel_id)
        assert len(cleared_records) == 0

    finally:
        conn.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        conn.execute("DELETE FROM chat_memory WHERE novel_id = ?", (novel_id,))
        conn.commit()
