# -*- coding: utf-8 -*-
import sqlite3
import json
from datetime import datetime
import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# 新增 opencc 套件，用於簡體轉繁體
try:
    from opencc import OpenCC
    _s2t_converter = OpenCC('s2t')
    # 進行安全自我檢測，防止 Windows 環境下 opencc 造成中文字串編碼損毀 (Mojibake)
    if _s2t_converter.convert("測試") != "測試":
        _s2t_converter = None
except Exception:
    # 若套件未安裝或載入失敗，fallback 為 identity function
    _s2t_converter = None

def _to_traditional(text):
    """將傳入的文字從簡體轉換為繁體。若非字串或轉換器不可用，直接回傳原值。"""
    if isinstance(text, str) and _s2t_converter:
        try:
            return _s2t_converter.convert(text)
        except Exception:
            return text
    return text

def _convert_obj_to_traditional(obj):
    """遞迴將物件內所有字串轉換為繁體（用於 dict/list 結構）。"""
    if isinstance(obj, str):
        return _to_traditional(obj)
    if isinstance(obj, list):
        return [_convert_obj_to_traditional(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _convert_obj_to_traditional(v) for k, v in obj.items()}
    return obj

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from .env file
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

DB_PATH = os.path.join(PROJECT_ROOT, "data", "novel_factory.db")

# --- Agent Default Configurations from .env ---
AGENT_DEFAULTS = {
    "global": {
        "model": os.getenv("MODEL_GLOBAL", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "architect": {
        "model": os.getenv("MODEL_ARCHITECT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 32768,
        "enable_thinking": 0
    },
    "character": {
        "model": os.getenv("MODEL_CHARACTER") or os.getenv("MODEL_STORY", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 32768,
        "enable_thinking": 0
    },
    "volumes": {
        "model": os.getenv("MODEL_VOLUMES") or os.getenv("MODEL_ARCHITECT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "volume_skeleton": {
        "model": os.getenv("MODEL_VOLUME_SKELETON") or os.getenv("MODEL_PLOT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "plot": {
        "model": os.getenv("MODEL_PLOT") or os.getenv("MODEL_CRITIC", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "writer": {
        "model": os.getenv("MODEL_WRITER", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "editor": {
        "model": os.getenv("MODEL_EDITOR", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    },
    "copilot": {
        "model": os.getenv("MODEL_COPILOT", "patcher-main"),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 16384,
        "enable_thinking": 0
    }
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn

