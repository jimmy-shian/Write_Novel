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

def get_worldview_patches(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT worldview_patches FROM novels WHERE id = ?", (novel_id,)).fetchone()
    conn.close()
    if row and row["worldview_patches"]:
        try:
            return json.loads(row["worldview_patches"])
        except:
            return []
    return []

def add_worldview_patch(novel_id, category, details, source_chapter_index):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT worldview_patches FROM novels WHERE id = ?", (novel_id,)).fetchone()
    patches = []
    if row and row["worldview_patches"]:
        try:
            patches = json.loads(row["worldview_patches"])
        except:
            patches = []
    patches.append({
        "category": _to_traditional(category),
        "details": _to_traditional(details),
        "source_chapter": source_chapter_index,
        "created_at": datetime.now().isoformat()
    })
    cursor.execute("UPDATE novels SET worldview_patches = ? WHERE id = ?", (json.dumps(patches, ensure_ascii=False), novel_id))
    conn.commit()
    conn.close()

def mark_downstream_dirty(novel_id, source_chapter_index):
    """
    Marks downstream volumes and chapters as dirty (Lazy Realignment Protocol)
    to terminate immediate LLM cascades.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Mark chapters with index > source_chapter_index as dirty
    cursor.execute("UPDATE chapters SET is_dirty = 1 WHERE novel_id = ? AND chapter_index > ?", (novel_id, source_chapter_index))
    
    # 2. Mark latest plot_chapters (outlines) record as dirty
    cursor.execute("UPDATE plot_chapters SET is_dirty = 1 WHERE novel_id = ?", (novel_id,))
    
    # 3. Mark downstream volumes as dirty
    vols = get_volumes(novel_id)
    source_volume = get_chapter_volume_index(vols, source_chapter_index)
    cursor.execute("UPDATE volumes SET is_dirty = 1 WHERE novel_id = ? AND volume_index > ?", (novel_id, source_volume))
    
    conn.commit()
    conn.close()

def apply_worldview_patch(novel_id, category, details):
    """
    Adapter function that updates the patches list and appends to worldview lists.
    """
    add_worldview_patch(novel_id, category, details, 0)
    append_worldbuilding_list(novel_id, "foreshadowing_seeds", f"[NEW_WORLD_LAW: {category}] {details}")

# Alias to support agents.py imports seamlessly
mark_subsequent_dirty = mark_downstream_dirty

# --- CHAPTERS BACKUP FUNCTIONS (P0-1) ---

def validate_worldview_schema(content):
    from backend.schemas.worldview import validate_worldview_schema as _validate_worldview_schema
    return _validate_worldview_schema(content)

# --- WORLDBUILDING (VERSIONED) ---
def get_latest_worldbuilding(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_worldbuilding_history(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT version, created_at FROM worldbuilding WHERE novel_id = ? ORDER BY version DESC",
        (novel_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_worldbuilding_by_version(novel_id, version):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM worldbuilding WHERE novel_id = ? AND version = ?",
        (novel_id, version)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def save_worldbuilding(novel_id, content, validate=True):
    if validate:
        valid, errors, warnings = validate_worldview_schema(content)
        if not valid:
            raise ValueError(f'世界觀結構驗證失敗: {";".join(errors)}')
        if warnings:
            print(f'[WARN] Worldview validation warnings for novel {novel_id}: {";".join(warnings)}')
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM worldbuilding WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO worldbuilding (novel_id, content, version) VALUES (?, ?, ?)",
        (novel_id, _to_traditional(content), next_version)
    )
    conn.commit()
    conn.close()
    return next_version

# --- CHARACTERS (VERSIONED) ---

def parse_worldview_to_json(content):
    from backend.schemas.worldview import parse_worldview_to_json as _parse_worldview_to_json
    return _parse_worldview_to_json(content)

def append_foreshadowing(novel_id, new_seed):
    wb = get_latest_worldbuilding(novel_id)
    if not wb:
        return None
    
    current_content = wb["content"]
    if current_content and current_content.strip().startswith("{"):
        try:
            parsed = parse_worldview_to_json(current_content)
            if "foreshadowing_seeds" not in parsed:
                parsed["foreshadowing_seeds"] = []
            parsed["foreshadowing_seeds"].append(new_seed)
            return save_worldbuilding(novel_id, json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[ERROR] JSON append failed: {e}. Falling back to text append.")

    if "伏筆種子" in current_content:
        parts = current_content.split("【伏筆種子】")
        if len(parts) > 1:
            new_part = parts[1]
            if new_part.strip():
                lines = new_part.strip().split("\n")
                last_idx = len(lines) - 1
                while last_idx >= 0 and not lines[last_idx].strip():
                    last_idx -= 1
                if last_idx >= 0:
                    lines.insert(last_idx + 1, f"  • {new_seed}")
                    new_part = "\n".join(lines)
            parts[1] = new_part
            new_content = "【伏筆種子】".join(parts)
        else:
            new_content = current_content + f"\n  • {new_seed}"
    else:
        new_content = current_content + f"\n\n【伏筆種子】\n  • {new_seed}"
    
    return save_worldbuilding(novel_id, new_content)


def append_worldbuilding_list(novel_id, key_section, new_item):
    wb = get_latest_worldbuilding(novel_id)
    if not wb:
        return None
    
    current_content = wb["content"]
    parsed = parse_worldview_to_json(current_content)
    
    if key_section not in parsed or not isinstance(parsed[key_section], list):
        parsed[key_section] = []
        
    if isinstance(new_item, list):
        for item in new_item:
            if isinstance(item, str) and item not in parsed[key_section]:
                parsed[key_section].append(item)
    else:
        if isinstance(new_item, str) and new_item not in parsed[key_section]:
            parsed[key_section].append(new_item)
            
    return save_worldbuilding(novel_id, json.dumps(parsed, ensure_ascii=False, indent=2))


# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.characters import *
from backend.persistence.repositories.foreshadowing import *
