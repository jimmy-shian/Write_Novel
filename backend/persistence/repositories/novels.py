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

def update_novel_pipeline_prompt(novel_id, pipeline_prompt):
    formatted = _to_traditional(pipeline_prompt)
    conn = get_db_connection()
    cursor = conn.cursor()
    # 寫入去重檢查：如果內容相同則跳過寫入
    row = cursor.execute("SELECT pipeline_prompt FROM novels WHERE id = ?", (novel_id,)).fetchone()
    if row and row["pipeline_prompt"] == formatted:
        return
    cursor.execute(
        "UPDATE novels SET pipeline_prompt = ? WHERE id = ?",
        (formatted, novel_id)
    )
    conn.commit()

def get_novel(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
    return dict(row) if row else None

def list_novels():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT * FROM novels ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def delete_novel(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    conn.commit()

RESET_CONTENT_SCOPES = ("worldbuilding", "characters", "plot", "chapters", "chat")

def reset_novel_content(novel_id, scopes=None):
    """
    清空小說的已生成內容（預設全部，保留 id, title, genre, style, pipeline_prompt）。

    scopes: 可選的清除範圍子集，例如 ["worldbuilding", "characters", "plot", "chapters", "chat"]。
      - None / 空 / 包含 "all" 視為全部清除（相容舊行為）。
      - worldbuilding: worldbuilding 表 + novels.worldview_patches
      - characters: characters 表
      - plot: volumes 表 + plot_chapters 表
      - chapters: chapters 表
      - chat: chat_memory 表 + pipeline_locks 表
    回傳實際執行的 scopes 清單。
    """
    if scopes is None or (isinstance(scopes, (list, tuple, set)) and len(scopes) == 0):
        effective = list(RESET_CONTENT_SCOPES)
    else:
        if isinstance(scopes, str):
            scopes = [scopes]
        effective = [s for s in scopes if s != "all"]
        if len(effective) == 0:
            effective = list(RESET_CONTENT_SCOPES)
        invalid = [s for s in effective if s not in RESET_CONTENT_SCOPES]
        if invalid:
            raise ValueError(f"不支援的清除範圍: {invalid}，允許值: {list(RESET_CONTENT_SCOPES)}")
        # 去重並保持定義順序
        effective = [s for s in RESET_CONTENT_SCOPES if s in effective]

    conn = get_db_connection()
    cursor = conn.cursor()
    if "worldbuilding" in effective:
        cursor.execute("DELETE FROM worldbuilding WHERE novel_id = ?", (novel_id,))
        cursor.execute("UPDATE novels SET worldview_patches = '[]' WHERE id = ?", (novel_id,))
    if "characters" in effective:
        cursor.execute("DELETE FROM characters WHERE novel_id = ?", (novel_id,))
    if "plot" in effective:
        cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
    if "chapters" in effective:
        cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
    if "chat" in effective:
        cursor.execute("DELETE FROM chat_memory WHERE novel_id = ?", (novel_id,))
        try:
            cursor.execute("DELETE FROM pipeline_locks WHERE novel_id = ?", (novel_id,))
        except sqlite3.OperationalError:
            pass
    conn.commit()
    return effective

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
