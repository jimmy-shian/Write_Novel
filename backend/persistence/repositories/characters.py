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

def get_latest_characters(novel_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM characters WHERE novel_id = ? ORDER BY version DESC LIMIT 1",
        (novel_id,)
    ).fetchone()
    conn.close()
    if row:
        data = dict(row)
        try:
            from backend.models.parsers import extract_json_block
            data["parsed_data"] = extract_json_block(data["json_data"])
        except:
            data["parsed_data"] = {}
        return data
    return None


def clean_and_deduplicate_characters(characters_list):
    if not isinstance(characters_list, list):
        return characters_list
        
    cleaned_chars = []
    
    # 1. Filter out invalid/placeholder characters
    placeholder_names = {
        "新登場的次要角色", "待補充", "暫無", "placeholder", "新角色", "路人", 
        "客棧老闆", "符合人設說話風格", "todo", "新登場次要角色"
    }
    
    for c in characters_list:
        if not isinstance(c, dict):
            continue
        name = c.get("name", "").strip()
        if not name:
            continue
            
        # If name is a placeholder, skip
        is_placeholder = False
        for pn in placeholder_names:
            if pn in name.lower() or name.lower() in pn:
                is_placeholder = True
                break
        if is_placeholder:
            continue
            
        # Clean fields in the character dictionary
        cleaned_c = {}
        for k, v in c.items():
            if isinstance(v, str):
                v_clean = v.strip()
                # If value is a placeholder text, make it empty
                if any(p in v_clean.lower() for p in ["符合人設說話風格", "請填入", "待定", "暫無", "待補充"]):
                    v_clean = ""
                cleaned_c[k] = v_clean
            elif isinstance(v, list):
                # Clean elements of lists
                cleaned_list = []
                for x in v:
                    if isinstance(x, str):
                        x_clean = x.strip()
                        if not any(p in x_clean.lower() for p in ["符合人設說話風格", "請填入", "待定", "暫無", "待補充"]):
                            cleaned_list.append(x_clean)
                    else:
                        cleaned_list.append(x)
                cleaned_c[k] = cleaned_list
            else:
                cleaned_c[k] = v
        cleaned_chars.append(cleaned_c)
        
    # Helper to get core name
    def get_core_name(name_str):
        if not name_str:
            return ""
        import re
        # Remove content in parentheses
        name_str = re.sub(r'[\(（].*?[\)）]', '', name_str)
        # Remove content after hyphens, dashes, colons or spaces
        for separator in ['-', '–', '—', '_', ':', '：', ' ', '\t']:
            if separator in name_str:
                parts = name_str.split(separator)
                if parts[0].strip():
                    name_str = parts[0]
        return name_str.strip()

    # Helper to merge two characters
    def merge_two_characters_backend(c1, c2):
        name1 = c1.get("name", "")
        name2 = c2.get("name", "")
        
        chosen_name = name1
        if name2 and len(name2) < len(name1):
            chosen_name = name2
        if not chosen_name:
            chosen_name = name1 or name2
            
        merged = {"name": chosen_name}
        
        # Field: role
        r1 = c1.get("role", "")
        r2 = c2.get("role", "")
        merged["role"] = r1 if len(str(r1)) >= len(str(r2)) else r2
        
        # Field: entry_phase
        ep1 = c1.get("entry_phase", "")
        ep2 = c2.get("entry_phase", "")
        merged["entry_phase"] = ep1 if ep1 else ep2
        
        # Field: personality (list)
        p1 = c1.get("personality", [])
        p2 = c2.get("personality", [])
        if isinstance(p1, str): p1 = [p1]
        if isinstance(p2, str): p2 = [p2]
        p_merged = list(set((p1 or []) + (p2 or [])))
        merged["personality"] = [x for x in p_merged if x]
        
        # Text fields
        for field in ["want", "need", "fatal_flaw", "motivation", "arc", "speech_style"]:
            val1 = c1.get(field, "")
            val2 = c2.get(field, "")
            if val1 and val2:
                if val1.strip().lower() == val2.strip().lower():
                    merged[field] = val1
                else:
                    merged[field] = val1 if len(str(val1)) >= len(str(val2)) else val2
            else:
                merged[field] = val1 or val2
                
        # Relationships (list of dicts)
        rel1 = c1.get("relationships", []) or []
        rel2 = c2.get("relationships", []) or []
        if not isinstance(rel1, list): rel1 = [rel1]
        if not isinstance(rel2, list): rel2 = [rel2]
        
        merged_rels = []
        rel_by_target = {}
        for r in rel1 + rel2:
            if not isinstance(r, dict):
                continue
            target = r.get("with")
            if not target:
                continue
            target_core = get_core_name(target)
            if target_core not in rel_by_target:
                rel_by_target[target_core] = r.copy()
            else:
                existing = rel_by_target[target_core]
                t_type = r.get("type", "")
                e_type = existing.get("type", "")
                if t_type and t_type not in e_type:
                    existing["type"] = f"{e_type} / {t_type}" if e_type else t_type
                t_evo = r.get("evolution", "")
                e_evo = existing.get("evolution", "")
                if t_evo and t_evo not in e_evo:
                    existing["evolution"] = f"{e_evo}。{t_evo}" if e_evo else t_evo
                    
        merged["relationships"] = list(rel_by_target.values())
        return merged

    # 2. Group by core name and merge
    merged_by_core = {}
    core_order = []  # To preserve original ordering of appearance
    
    for c in cleaned_chars:
        name = c.get("name", "")
        core = get_core_name(name)
        if not core:
            continue
            
        if core not in merged_by_core:
            merged_by_core[core] = c
            core_order.append(core)
        else:
            # Merge with existing
            existing = merged_by_core[core]
            merged_by_core[core] = merge_two_characters_backend(existing, c)
            
    # Reconstruct list
    result = [merged_by_core[core] for core in core_order]
    return result

def save_characters(novel_id, json_data):
    if isinstance(json_data, dict) or isinstance(json_data, list):
        # 先將字典/清單內的字串進行繁體轉換
        json_data = _convert_obj_to_traditional(json_data)
        
        # 🚨 自動執行去重與合併 🚨
        if isinstance(json_data, dict) and "characters" in json_data:
            json_data["characters"] = clean_and_deduplicate_characters(json_data["characters"])
        elif isinstance(json_data, list):
            json_data = clean_and_deduplicate_characters(json_data)
            
        json_str = json.dumps(json_data, ensure_ascii=False)
    else:
        json_str = _to_traditional(json_data)
        try:
            from backend.models.parsers import extract_json_block
            parsed = extract_json_block(json_str)
            if isinstance(parsed, dict) and "characters" in parsed:
                parsed["characters"] = clean_and_deduplicate_characters(parsed["characters"])
                json_str = json.dumps(parsed, ensure_ascii=False)
            elif isinstance(parsed, list):
                parsed = clean_and_deduplicate_characters(parsed)
                json_str = json.dumps(parsed, ensure_ascii=False)
        except:
            pass
        
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT MAX(version) as max_v FROM characters WHERE novel_id = ?",
        (novel_id,)
    ).fetchone()
    next_version = (row["max_v"] or 0) + 1
    
    cursor.execute(
        "INSERT INTO characters (novel_id, json_data, version) VALUES (?, ?, ?)",
        (novel_id, json_str, next_version)
    )
    conn.commit()
    conn.close()
    return next_version

# --- PLOT CHAPTERS (VERSIONED) ---

def normalize_char_index(raw_index, total_chars, source='unknown'):
    if 0 <= raw_index < total_chars:
        return raw_index
    if 1 <= raw_index <= total_chars:
        print(f"[WARN] {source}: received 1-based index {raw_index}, converting to 0-based {raw_index - 1}")
        return raw_index - 1
    raise IndexError(f"Character index {raw_index} out of range [0, {total_chars}) from {source}")

def update_character_field(novel_id, char_index, field_name, new_value):
    if field_name not in ALLOWED_CHARACTER_FIELDS:
        print(f"[ERROR] Field '{field_name}' is not in character fields whitelist")
        return None
        
    char_data = get_latest_characters(novel_id)
    if not char_data or "parsed_data" not in char_data:
        return None
    
    parsed = char_data["parsed_data"]
    if "characters" not in parsed:
        return None
    
    try:
        norm_idx = normalize_char_index(char_index, len(parsed["characters"]), source='update_character_field')
    except IndexError:
        return None
    
    parsed["characters"][norm_idx][field_name] = new_value
    
    return save_characters(novel_id, parsed)


def update_character_single_field(novel_id, char_index, field_name, new_value):
    result = update_character_field(novel_id, char_index, field_name, new_value)
    if result:
        return {"status": "success", "version": result}
    return {"status": "error", "message": "Failed to update character field"}


# Cross-repository imports used by legacy domain functions during runtime.
from backend.persistence.schema import db_init, sync_agent_configs_from_env
from backend.persistence.repositories.agent_runs import *
from backend.persistence.repositories.novels import *
from backend.persistence.repositories.volumes import *
from backend.persistence.repositories.worldbuilding import *
from backend.persistence.repositories.chapters import *
from backend.persistence.repositories.pipeline_locks import *
from backend.persistence.repositories.foreshadowing import *
