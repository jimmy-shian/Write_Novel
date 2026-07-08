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

def create_novel(novel_id, title, genre, style):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO novels (id, title, genre, style, pipeline_prompt) VALUES (?, ?, ?, ?, ?)",
        (novel_id, _to_traditional(title), genre, style, "")
    )
    conn.commit()
    conn.close()

def update_novel_pipeline_prompt(novel_id, pipeline_prompt):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE novels SET pipeline_prompt = ? WHERE id = ?",
        (_to_traditional(pipeline_prompt), novel_id)
    )
    conn.commit()
    conn.close()

def get_novel(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_novels():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM novels ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_novel(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    conn.commit()
    conn.close()

# --- VOLUMES (篇卷) HELPERS ---

# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *
