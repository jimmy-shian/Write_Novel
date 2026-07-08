# -*- coding: utf-8 -*-
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from backend.common.utils import deep_merge_dict, safe_filename
from backend.persistence.connection import (
    AGENT_DEFAULTS,
    DB_PATH,
    _convert_obj_to_traditional,
    _to_traditional,
    get_db_connection,
)
try:
    from backend.schemas.agent_json import CHARACTER_BASIC_FIELDS
except Exception:
    CHARACTER_BASIC_FIELDS = []

def save_prompt_override(template_name: str, key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO prompt_overrides (template_name, key, value)
        VALUES (?, ?, ?)
        ON CONFLICT(template_name, key) DO UPDATE SET
            value = excluded.value
        """,
        (template_name, key, value)
    )
    conn.commit()
    conn.close()

def get_prompt_override(template_name: str, key: str) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM prompt_overrides WHERE template_name = ? AND key = ?",
        (template_name, key)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# --- LAST AGENT RUN TRACKING ---
def save_last_agent_run(novel_id, agent_name, input_data, output_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO last_agent_run (novel_id, agent_name, input_data, output_data, timestamp)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(novel_id) DO UPDATE SET
            agent_name = excluded.agent_name,
            input_data = excluded.input_data,
            output_data = excluded.output_data,
            timestamp = CURRENT_TIMESTAMP
        """,
        (novel_id, agent_name, input_data, output_data)
    )
    conn.commit()
    conn.close()

def get_last_agent_run(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM last_agent_run WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

# --- NOVELS CRUD ---

def get_agent_configs():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM agent_configs").fetchall()
    conn.close()
    return {r["agent_name"]: dict(r) for r in rows}

def save_agent_config(agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO agent_configs (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, int(enable_thinking)))
    conn.commit()
    conn.close()

# --- INCREMENTAL UPDATE FUNCTIONS ---

# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *
