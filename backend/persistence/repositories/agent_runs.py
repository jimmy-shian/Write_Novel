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

# --- RAM CACHES FOR STATIC/SEMI-STATIC DATA ---
_AGENT_CONFIGS_CACHE: Optional[Dict[str, dict]] = None
_AGENT_CONFIGS_DATA_VERSION: Optional[int] = None
_PROMPT_OVERRIDE_CACHE: Dict[tuple, Optional[str]] = {}

def get_db_data_version(conn=None) -> int:
    """取得 SQLite 資料庫的 data_version，用於跨連線快取失效檢查"""
    c = conn or get_db_connection()
    try:
        row = c.execute("PRAGMA data_version;").fetchone()
        return row[0] if row else 0
    except Exception:
        return 0

def save_prompt_override(template_name: str, key: str, value: str):
    cache_key = (template_name, key)
    # 寫入去重：若記憶體快取中值完全相同，直接跳過 DB Write
    if _PROMPT_OVERRIDE_CACHE.get(cache_key) == value:
        return

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
    _PROMPT_OVERRIDE_CACHE[cache_key] = value

def get_prompt_override(template_name: str, key: str) -> Optional[str]:
    cache_key = (template_name, key)
    if cache_key in _PROMPT_OVERRIDE_CACHE:
        return _PROMPT_OVERRIDE_CACHE[cache_key]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM prompt_overrides WHERE template_name = ? AND key = ?",
        (template_name, key)
    )
    row = cursor.fetchone()
    val = row[0] if row else None
    _PROMPT_OVERRIDE_CACHE[cache_key] = val
    return val

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

def get_last_agent_run(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM last_agent_run WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    return dict(row) if row else None

# --- AGENT CONFIGS (WITH RAM CACHE & DEDUPLICATION) ---

def invalidate_agent_configs_cache():
    """使 Agent Config 記憶體快取失效"""
    global _AGENT_CONFIGS_CACHE, _AGENT_CONFIGS_DATA_VERSION
    _AGENT_CONFIGS_CACHE = None
    _AGENT_CONFIGS_DATA_VERSION = None

def get_agent_configs():
    global _AGENT_CONFIGS_CACHE, _AGENT_CONFIGS_DATA_VERSION
    conn = get_db_connection()
    current_ver = get_db_data_version(conn)
    if _AGENT_CONFIGS_CACHE is not None and _AGENT_CONFIGS_DATA_VERSION == current_ver:
        return _AGENT_CONFIGS_CACHE

    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM agent_configs").fetchall()
    configs = {r["agent_name"]: dict(r) for r in rows}
    _AGENT_CONFIGS_CACHE = configs
    _AGENT_CONFIGS_DATA_VERSION = current_ver
    return configs

def save_agent_config(agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking):
    global _AGENT_CONFIGS_CACHE
    # 寫入去重檢查：比對目前快取，若所有欄位完全無變更則直接跳過寫入
    current_configs = get_agent_configs()
    existing = current_configs.get(agent_name)
    if existing:
        if (
            existing.get("api_key") == api_key and
            existing.get("base_url") == base_url and
            existing.get("model") == model and
            float(existing.get("temperature", 0)) == float(temperature) and
            float(existing.get("top_p", 0)) == float(top_p) and
            int(existing.get("max_tokens", 0)) == int(max_tokens) and
            int(existing.get("enable_thinking", 0)) == int(enable_thinking)
        ):
            # 無任何變更，跳過 DB Write 零 I/O
            return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO agent_configs (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, enable_thinking)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (agent_name, api_key, base_url, model, temperature, top_p, max_tokens, int(enable_thinking)))
    conn.commit()
    invalidate_agent_configs_cache()

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
