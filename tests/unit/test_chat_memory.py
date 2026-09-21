# -*- coding: utf-8 -*-
"""
chat_memory 儲存層與 API 單元測試：
- save / get / clear（含 message_type 過濾與 thinking 保留）
- API 端點：查詢、單則刪除
"""
from fastapi.testclient import TestClient

from backend.app import app
from backend.persistence.repositories.chat_memory import (
    save_chat_message,
    get_chat_memory,
    clear_chat_memory,
)

client = TestClient(app)


def test_chat_memory_crud_and_query_all(novel_factory):
    novel_id = novel_factory(title="Chat Test Novel", genre="Fantasy", style="Standard")

    # 寫入不同類型訊息
    save_chat_message(novel_id, "director", "【總監通報】結構完整", thinking="思考細節1", message_type="chat")
    save_chat_message(novel_id, "assistant", "第 1 章骨架建立完畢", thinking=None, message_type="pipeline")
    save_chat_message(novel_id, "user", "請加強主角動機", thinking=None, message_type="chat")

    # 查詢全部（message_type=None 不過濾）
    all_records = get_chat_memory(novel_id, limit=50, message_type=None)
    assert len(all_records) == 3
    types = [r["message_type"] for r in all_records]
    assert "pipeline" in types
    assert "chat" in types

    # thinking 欄位應被保留
    director_msg = next(r for r in all_records if r["role"] == "director")
    assert director_msg["thinking"] == "思考細節1"
    assert director_msg["content"] == "【總監通報】結構完整"

    # 依 message_type 過濾
    pipeline_only = get_chat_memory(novel_id, limit=50, message_type="pipeline")
    assert len(pipeline_only) == 1
    assert pipeline_only[0]["role"] == "assistant"

    # API：GET chat-memory
    res = client.get(f"/api/novels/{novel_id}/chat-memory?limit=50")
    assert res.status_code == 200
    data = res.json()
    assert "chat_memory" in data
    assert len(data["chat_memory"]) == 3

    # API：單則刪除
    first_msg_id = data["chat_memory"][0]["id"]
    del_res = client.delete(f"/api/novels/{novel_id}/chat-memory/{first_msg_id}")
    assert del_res.status_code == 200
    after_del = get_chat_memory(novel_id)
    assert len(after_del) == 2
    assert not any(m["id"] == first_msg_id for m in after_del)

    # 依 message_type 清除
    clear_chat_memory(novel_id, message_type="pipeline")
    after_type_clear = get_chat_memory(novel_id)
    assert not any(m["message_type"] == "pipeline" for m in after_type_clear)

    # 全部清除
    clear_chat_memory(novel_id)
    assert len(get_chat_memory(novel_id)) == 0
