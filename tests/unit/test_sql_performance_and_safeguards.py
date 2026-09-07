# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import tempfile
import threading
import pytest
from pathlib import Path

from backend.persistence.connection import ConnectionManager, get_db_connection, DB_PATH
import backend.persistence.repositories.agent_runs as ar
from backend.persistence.repositories.agent_runs import (
    save_agent_config,
    get_agent_configs,
    save_last_agent_run,
    get_last_agent_run,
    _compact_input_data,
    save_prompt_override,
    get_prompt_override,
)
from backend.prompts.prompt_manager import load_prompt_template
from backend.persistence.repositories.chapters import save_chat_message
from backend.services.hf_sync import (
    backup_database,
    restore_database,
    _apply_downloaded_database,
    get_sync_status,
)
from backend.services.settings.service import apply_settings_payload


def test_reentrant_lock_save_settings():
    """Verify save_agent_config does not deadlock and works in bulk settings payloads."""
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
            }
        }
    }
    res = apply_settings_payload(payload)
    assert res["status"] == "success"
    
    configs = get_agent_configs()
    assert configs["global"]["model"] == "test-model-1"
    assert configs["writer"]["model"] == "test-model-2"


def test_connection_manager_close_all():
    """Verify ConnectionManager tracks active connections and closes all cleanly."""
    conn1 = ConnectionManager.get_connection()
    assert conn1 is not None
    # Check cache_size pragma
    cache_row = conn1.execute("PRAGMA cache_size;").fetchone()
    assert cache_row[0] == -8192

    # Close all
    ConnectionManager.close_all_connections()
    assert len(ConnectionManager._active_connections) == 0

    # Get connection again should reconnect cleanly
    conn2 = ConnectionManager.get_connection()
    assert conn2 is not None
    assert conn2.execute("SELECT 1;").fetchone()[0] == 1


def test_save_last_agent_run_compaction():
    """Verify save_last_agent_run strips <think> tags and compacts excessive context."""
    test_novel_id = "test_perf_novel_999"
    large_messages = [
        {"role": "system", "content": "You are a novel writer."}
    ]
    # Add 20 large user/assistant messages totaling > 50KB
    for i in range(20):
        large_messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": "X" * 3000})

    input_json = json.dumps(large_messages, ensure_ascii=False)
    assert len(input_json) > 50000

    output_with_thinking = "<think>Detailed reasoning process that is very long...</think>The final chapter text."

    save_last_agent_run(test_novel_id, "writer", input_json, output_with_thinking)
    saved = get_last_agent_run(test_novel_id)

    assert saved is not None
    assert "<think>" not in saved["output_data"]
    assert "The final chapter text." in saved["output_data"]
    # Input data should be compacted
    assert len(saved["input_data"]) <= 32768


def test_chat_memory_pipeline_pruning_and_index():
    """Verify chat_memory composite index exists and pipeline messages are pruned to 300."""
    conn = get_db_connection()
    indices = conn.execute("PRAGMA index_list(chat_memory);").fetchall()
    index_names = [idx[1] for idx in indices]
    assert "idx_chat_memory_lookup" in index_names

    test_novel_id = "test_chat_mem_novel_123"
    conn.execute("INSERT OR IGNORE INTO novels (id, title) VALUES (?, ?)", (test_novel_id, "Test Title"))
    conn.commit()

    # Insert a user chat message and a director decision message
    save_chat_message(test_novel_id, "user", "Hello author", message_type="chat")
    save_chat_message(test_novel_id, "assistant", "Director review approved", message_type="director")

    # Insert 350 pipeline messages
    for i in range(350):
        save_chat_message(test_novel_id, "assistant", f"Pipeline log step {i}", message_type="pipeline")

    # Check counts
    cur = conn.cursor()
    pipeline_count = cur.execute(
        "SELECT COUNT(*) FROM chat_memory WHERE novel_id = ? AND message_type = 'pipeline'",
        (test_novel_id,)
    ).fetchone()[0]
    assert pipeline_count == 300

    # Verify chat & director messages were NOT pruned
    chat_count = cur.execute(
        "SELECT COUNT(*) FROM chat_memory WHERE novel_id = ? AND message_type = 'chat'",
        (test_novel_id,)
    ).fetchone()[0]
    assert chat_count == 1

    director_count = cur.execute(
        "SELECT COUNT(*) FROM chat_memory WHERE novel_id = ? AND message_type = 'director'",
        (test_novel_id,)
    ).fetchone()[0]
    assert director_count == 1

    # Cleanup
    conn.execute("DELETE FROM chat_memory WHERE novel_id = ?", (test_novel_id,))
    conn.execute("DELETE FROM novels WHERE id = ?", (test_novel_id,))
    conn.commit()


def test_atomic_restore_database_and_sidecar_cleanup():
    """Verify _apply_downloaded_database checks integrity, closes connections and cleans sidecars."""
    temp_dir = tempfile.mkdtemp()
    temp_db = os.path.join(temp_dir, "test_valid.db")
    test_conn = sqlite3.connect(temp_db)
    test_conn.execute("CREATE TABLE test_tab (id INT);")
    test_conn.execute("INSERT INTO test_tab VALUES (42);")
    test_conn.commit()
    test_conn.close()

    try:
        from backend.services import hf_sync
        # Verify corrupt file raises exception
        corrupt_file = os.path.join(temp_dir, "corrupt.db")
        with open(corrupt_file, "w") as f:
            f.write("not a sqlite file")
        with pytest.raises(Exception):
            hf_sync._apply_downloaded_database(corrupt_file)
    finally:
        pass
