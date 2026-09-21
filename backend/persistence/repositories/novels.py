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

def update_novel_metadata(novel_id: str, title: Optional[str] = None, genre: Optional[str] = None, style: Optional[str] = None, pipeline_prompt: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if title is not None:
        updates.append("title = ?")
        params.append(_to_traditional(str(title).strip()))
    if genre is not None:
        updates.append("genre = ?")
        params.append(str(genre).strip())
    if style is not None:
        updates.append("style = ?")
        params.append(str(style).strip())
    if pipeline_prompt is not None:
        updates.append("pipeline_prompt = ?")
        params.append(_to_traditional(str(pipeline_prompt).strip()))
    if not updates:
        return
    params.append(novel_id)
    cursor.execute(f"UPDATE novels SET {', '.join(updates)} WHERE id = ?", params)
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
    # Explicitly cascade delete from all child tables to guarantee 100% clean-up
    cascade_tables = [
        "setting_systems", "conflict_signatures", "narrative_audits",
        "temporal_facts", "temporal_episodes", "temporal_entities",
        "story_terms", "draft_proposals", "foreshadowing_blueprints",
        "worldbuilding", "characters", "plot_chapters", "volumes",
        "chapters", "chat_memory", "pipeline_locks",
        "director_reviews", "chapter_memory", "arc_summaries",
        "geometry_nodes", "geometry_edges", "geometry_threads",
        "geometry_volumes", "geometry_arcs", "geometry_metadata",
    ]
    for table in cascade_tables:
        try:
            cursor.execute(f"DELETE FROM {table} WHERE novel_id = ?", (novel_id,))
        except sqlite3.OperationalError:
            pass
    cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    conn.commit()


def _clear_geometry_tables(cursor, novel_id):
    """清除敘事幾何拓撲（樹狀結構/心智圖）的 6 張衍生表。"""
    for table in (
        "geometry_nodes", "geometry_edges", "geometry_threads",
        "geometry_volumes", "geometry_arcs", "geometry_metadata",
    ):
        try:
            cursor.execute(f"DELETE FROM {table} WHERE novel_id = ?", (novel_id,))
        except sqlite3.OperationalError:
            pass


def _clear_foreshadowing_blueprint(cursor, novel_id):
    try:
        cursor.execute("DELETE FROM foreshadowing_blueprints WHERE novel_id = ?", (novel_id,))
    except sqlite3.OperationalError:
        pass

RESET_CONTENT_SCOPES = ("worldbuilding", "characters", "plot", "chapters", "chat")

def reset_novel_content(novel_id, scopes=None):
    """
    清空小說的已生成內容（預設全部，保留 id, title, genre, style, pipeline_prompt）。

    scopes: 可選的清除範圍子集，例如 ["worldbuilding", "characters", "plot", "chapters", "chat"]。
      - None / 空 / 包含 "all" 視為全部清除（相容舊行為）。
      - worldbuilding: worldbuilding 表 + novels.worldview_patches + setting_systems + 伏筆藍圖
      - characters: characters 表
      - plot: volumes 表 + plot_chapters 表 + 幾何拓撲樹狀結構 + 伏筆藍圖 + 衝突簽名
      - chapters: chapters 表 + 連動清除全書時序圖譜與自動術語（手動術語保留）
        + 幾何拓撲 + 草稿修訂提案 + 章節記憶/段落摘要/導演審查 + 敘事引擎簽名/審計
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
        try:
            cursor.execute("DELETE FROM setting_systems WHERE novel_id = ?", (novel_id,))
        except sqlite3.OperationalError:
            pass
        # 世界觀清空後，由其提煉的伏筆藍圖已成孤兒，一併清除避免殘留顯示
        _clear_foreshadowing_blueprint(cursor, novel_id)
    if "characters" in effective:
        cursor.execute("DELETE FROM characters WHERE novel_id = ?", (novel_id,))
    if "plot" in effective:
        cursor.execute("DELETE FROM plot_chapters WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM volumes WHERE novel_id = ?", (novel_id,))
        try:
            cursor.execute("DELETE FROM conflict_signatures WHERE novel_id = ?", (novel_id,))
        except sqlite3.OperationalError:
            pass
        # 分卷/章綱清空後，幾何拓撲樹狀結構與伏筆藍圖即成孤兒，必須連動清除，
        # 否則前端幾何畫布仍顯示舊樹（本次回報的主 bug）。
        _clear_geometry_tables(cursor, novel_id)
        _clear_foreshadowing_blueprint(cursor, novel_id)
    if "chapters" in effective:
        cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (novel_id,))
        # 模組化關聯：正文整批清除時連動清除衍生的時序圖譜與自動術語，以及長程衝突簽名與審查記錄；
        # 設定系統本體保留（世界觀還在），但用量計數歸零避免指向已刪章節。
        cursor.execute("DELETE FROM temporal_facts WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM temporal_episodes WHERE novel_id = ?", (novel_id,))
        cursor.execute("DELETE FROM temporal_entities WHERE novel_id = ?", (novel_id,))
        try:
            cursor.execute("DELETE FROM conflict_signatures WHERE novel_id = ?", (novel_id,))
            cursor.execute("DELETE FROM narrative_audits WHERE novel_id = ?", (novel_id,))
        except sqlite3.OperationalError:
            pass
        # 正文清空後，幾何節點的 chapter_start/end 全成孤兒，連動清除避免樹狀殘留；
        # 同時清除 per-chapter 衍生：草稿提案、章節記憶、段落摘要、導演審查、伏筆藍圖。
        _clear_geometry_tables(cursor, novel_id)
        _clear_foreshadowing_blueprint(cursor, novel_id)
        for table in (
            "draft_proposals", "chapter_memory", "arc_summaries", "director_reviews",
        ):
            try:
                cursor.execute(f"DELETE FROM {table} WHERE novel_id = ?", (novel_id,))
            except sqlite3.OperationalError:
                pass
        try:
            cursor.execute(
                "UPDATE setting_systems SET usage_count = 0, last_used_chapter = 0 WHERE novel_id = ?",
                (novel_id,),
            )
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute(
                "DELETE FROM story_terms WHERE novel_id = ? AND source_chapter IS NOT NULL",
                (novel_id,),
            )
        except sqlite3.OperationalError:
            # 舊 DB 尚未遷移 source_chapter 欄位時跳過（手動術語不受影響）
            pass
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
