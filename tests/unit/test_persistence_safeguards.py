# -*- coding: utf-8 -*-
"""
持久層防護與效能單元測試：
- 連線管理（可重入鎖、連線快取 pragma、close_all）
- agent run 記錄壓縮（剝離 thinking、收合超量 context）
- chat_memory 複合索引與 pipeline 訊息修剪
- 資料庫還原完整性檢查
- get_chapter 別名（防止 AttributeError 500）
"""
import json
import os
import tempfile

import pytest

from backend.persistence.connection import ConnectionManager, get_db_connection
from backend.persistence.repositories.agent_runs import (
    save_last_agent_run,
    get_last_agent_run,
)
from backend.persistence.repositories.chapters import (
    save_chapter,
    save_chat_message,
    get_chapter,
)
from backend.services.settings.service import apply_settings_payload


def test_reentrant_lock_save_settings():
    """save_agent_config 不得死鎖，且可套用整批設定。"""
    initial_configs = get_agent_configs_snapshot()
    try:
        payload = {
            "configs": {
                "global": {
                    "api_key": "test_key",
                    "base_url": "https://api.openai.com/v1",
                    "model": "test-model-1",
                    "temperature": 0.7,
                    "enable_thinking": 1,
                },
                "writer": {
                    "api_key": "test_key",
                    "base_url": "https://api.openai.com/v1",
                    "model": "test-model-2",
                    "temperature": 0.8,
                    "enable_thinking": 0,
                },
            }
        }
        res = apply_settings_payload(payload)
        assert res["status"] == "success"

        from backend.persistence.repositories.agent_runs import get_agent_configs

        configs = get_agent_configs()
        assert configs["global"]["model"] == "test-model-1"
        assert configs["writer"]["model"] == "test-model-2"
    finally:
        if initial_configs:
            apply_settings_payload({"configs": initial_configs})


def get_agent_configs_snapshot():
    from backend.persistence.repositories.agent_runs import get_agent_configs

    return get_agent_configs()


def test_connection_manager_close_all():
    """ConnectionManager 追蹤活躍連線，close_all 後可乾淨重連。"""
    conn1 = ConnectionManager.get_connection()
    assert conn1 is not None
    cache_row = conn1.execute("PRAGMA cache_size;").fetchone()
    assert cache_row[0] == -8192

    ConnectionManager.close_all_connections()
    assert len(ConnectionManager._active_connections) == 0

    conn2 = ConnectionManager.get_connection()
    assert conn2 is not None
    assert conn2.execute("SELECT 1;").fetchone()[0] == 1


def test_save_last_agent_run_compaction():
    """save_last_agent_run 應剝離 thinking 標籤並壓縮超量輸入。"""
    test_novel_id = "test_perf_novel_999"
    large_messages = [{"role": "system", "content": "You are a novel writer."}]
    for i in range(20):
        large_messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": "X" * 3000})

    input_json = json.dumps(large_messages, ensure_ascii=False)
    assert len(input_json) > 50000

    think_open = "<" + "think" + ">"
    think_close = "<" + "/think" + ">"
    output_with_thinking = f"{think_open}冗長推理過程{think_close}最終章節正文。"

    save_last_agent_run(test_novel_id, "writer", input_json, output_with_thinking)
    saved = get_last_agent_run(test_novel_id)

    assert saved is not None
    assert think_open not in saved["output_data"]
    assert "最終章節正文。" in saved["output_data"]
    # 輸入資料應被壓縮
    assert len(saved["input_data"]) <= 32768


def test_chat_memory_pipeline_pruning_and_index():
    """chat_memory 複合索引存在，且 pipeline 訊息修剪至 300 筆。"""
    conn = get_db_connection()
    indices = conn.execute("PRAGMA index_list(chat_memory);").fetchall()
    index_names = [idx[1] for idx in indices]
    assert "idx_chat_memory_lookup" in index_names

    test_novel_id = "test_chat_mem_novel_123"
    conn.execute("INSERT OR IGNORE INTO novels (id, title) VALUES (?, ?)", (test_novel_id, "Test Title"))
    conn.commit()

    try:
        save_chat_message(test_novel_id, "user", "Hello author", message_type="chat")
        save_chat_message(test_novel_id, "assistant", "Director review approved", message_type="director")

        # 插入 350 筆 pipeline 訊息
        for i in range(350):
            save_chat_message(test_novel_id, "assistant", f"Pipeline log step {i}", message_type="pipeline")

        cur = conn.cursor()
        pipeline_count = cur.execute(
            "SELECT COUNT(*) FROM chat_memory WHERE novel_id = ? AND message_type = 'pipeline'",
            (test_novel_id,),
        ).fetchone()[0]
        assert pipeline_count == 300

        # chat 與 director 訊息不得被修剪
        chat_count = cur.execute(
            "SELECT COUNT(*) FROM chat_memory WHERE novel_id = ? AND message_type = 'chat'",
            (test_novel_id,),
        ).fetchone()[0]
        assert chat_count == 1
        director_count = cur.execute(
            "SELECT COUNT(*) FROM chat_memory WHERE novel_id = ? AND message_type = 'director'",
            (test_novel_id,),
        ).fetchone()[0]
        assert director_count == 1
    finally:
        conn.execute("DELETE FROM chat_memory WHERE novel_id = ?", (test_novel_id,))
        conn.execute("DELETE FROM novels WHERE id = ?", (test_novel_id,))
        conn.commit()


def test_atomic_restore_database_rejects_corrupt_file():
    """_apply_downloaded_database 必須對損毀檔案拋出例外（完整性檢查）。"""
    temp_dir = tempfile.mkdtemp()
    corrupt_file = os.path.join(temp_dir, "corrupt.db")
    with open(corrupt_file, "w") as f:
        f.write("not a sqlite file")

    from backend.services import hf_sync

    with pytest.raises(Exception):
        hf_sync._apply_downloaded_database(corrupt_file)


def test_get_chapter_alias_and_persistence(novel_factory):
    """get_chapter 別名應能讀出 save_chapter 存入的資料，防止 500 AttributeError。"""
    novel_id = novel_factory(title="章節別名測試")
    save_chapter(novel_id, 1, "這是第 1 章正文內容，包含了詳細的故事推進情節。", "第一章概要", "思考過程")

    ch = get_chapter(novel_id, 1)
    assert ch is not None
    assert ch["chapter_index"] == 1
    assert "第 1 章正文內容" in ch["content"]